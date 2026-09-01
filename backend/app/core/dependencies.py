"""
Dependencias FastAPI compartilhadas.

`get_tenant_context` e a porta de entrada das rotas autenticadas:
- valida o JWT (Authorization: Bearer ...)
- extrai user_id + tenant_id
- confere que o usuario ainda existe, esta ativo, e pertence ao tenant do token
- retorna um TenantContext com a sessao do DB ja aberta

Esta dependencia DEVE ser usada por TODA rota que toca dados de tenant.
"""
from datetime import datetime, timezone
import hashlib
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.core.tenant_context import TenantContext
from app.models.tenant import Tenant
from app.models.api_key import ApiKey
from app.models.user import User

# tokenUrl aponta para a rota de login (a implementar)
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=True)

# Exportado para rotas que precisam do token bruto além do contexto
# (ex.: /auth/me lê o exp para a renovação deslizante da sessão).
oauth2_scheme = _oauth2_scheme

_credentials_exc = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Credenciais invalidas",
    headers={"WWW-Authenticate": "Bearer"},
)

# 402 quando a assinatura não está em dia. O frontend usa isso pra levar à tela
# de "regularizar pagamento".
_payment_required_exc = HTTPException(
    status_code=status.HTTP_402_PAYMENT_REQUIRED,
    detail="Assinatura inativa. Regularize o pagamento para continuar.",
)

# Rotas que continuam funcionando MESMO com assinatura inativa — senão a própria
# tela de pagamento (que precisa da identidade + status) não renderiza. O webhook
# e o checkout de billing são públicos (nem passam por aqui).
_BILLING_EXEMPT_SUFFIXES = (
    "/auth/me",
    "/auth/change-password",
    "/auth/set-password",
    "/auth/logout",
)


def _subscription_blocks(tenant: Tenant | None, now: datetime) -> bool:
    """True se o acesso deve ser bloqueado por assinatura. Tenants legados
    (status 'active', sem billing) NUNCA bloqueiam."""
    if tenant is None:
        return False
    st = tenant.subscription_status
    if st in ("suspended", "canceled"):
        return True
    # past_due só bloqueia depois que a tolerância (grace) vence.
    if st == "past_due" and tenant.grace_until is not None and now >= tenant.grace_until:
        return True
    return False


def _is_billing_exempt(path: str) -> bool:
    return "/billing/" in path or path.endswith(_BILLING_EXEMPT_SUFFIXES)


# ---------------------------------------------------------------------------
# Chave de API (acesso programatico, somente leitura)
# ---------------------------------------------------------------------------
# Metodos que MODIFICAM dado. A chave nasce com escopo "read" e a checagem e
# feita aqui, no portao, e nao em cada rota: rota nova entra protegida por
# padrao, sem ninguem precisar lembrar.
_METODOS_DE_ESCRITA = {"POST", "PUT", "PATCH", "DELETE"}

_api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)

_api_key_exc = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Chave de API invalida, revogada ou vencida.",
)
_api_key_readonly_exc = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Esta chave de API e somente leitura.",
)

_api_key_admin_exc = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Chave de API nao acessa a area administrativa.",
)


def hash_api_key(raw: str) -> str:
    """SHA-256 da chave. O banco guarda SO isto — nunca a chave."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_context_by_api_key(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    api_key: Annotated[str | None, Depends(_api_key_scheme)] = None,
) -> TenantContext | None:
    """Autentica pelo header X-API-Key. None = nao veio chave (tenta JWT).

    Devolve o MESMO TenantContext do login humano — de proposito: assim toda
    regra de isolamento por tenant que ja existe nos repositorios vale igual
    pra chave, sem caminho paralelo que possa divergir e vazar dado.
    """
    if not api_key:
        return None

    if request.method in _METODOS_DE_ESCRITA:
        raise _api_key_readonly_exc

    # Area administrativa e sobre IDENTIDADE, e a chave nao tem uma propria:
    # ela viaja com o user_id de quem a criou. Barrar o prefixo inteiro aqui
    # faz rota administrativa nova ja nascer fechada.
    if "/admin/" in request.url.path:
        raise _api_key_admin_exc

    chave = (
        db.query(ApiKey).filter(ApiKey.key_hash == hash_api_key(api_key)).one_or_none()
    )
    if chave is None or not chave.is_valid:
        raise _api_key_exc

    row = (
        db.query(Tenant).filter(Tenant.id == chave.tenant_id, Tenant.is_active.is_(True))
        .one_or_none()
    )
    if row is None:
        raise _api_key_exc

    # Marca o uso. Sem isto nao da pra responder "esta chave ainda e usada?"
    # na hora de limpar acesso antigo.
    chave.last_used_at = datetime.now(timezone.utc)
    chave.use_count = (chave.use_count or 0) + 1
    db.commit()

    return TenantContext(
        user_id=chave.created_by or chave.id,
        tenant_id=chave.tenant_id,
        role="viewer",          # papel mais baixo: a chave nunca administra
        db=db,
        user_name=f"chave: {chave.name}",
        via_api_key=True,
        # Leitura liberada nos modulos de dado. A escrita ja foi barrada acima.
        analytics_enabled=True, panel_enabled=True, map_enabled=True,
        demands_enabled=True, agenda_enabled=True, census_enabled=True,
        subscription_active=True,
    )


def get_tenant_context(
    request: Request,
    token: Annotated[str, Depends(_oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> TenantContext:
    # 1. Decodifica o JWT (assinatura, expiracao, formato). O middleware
    #    restrict_volunteer (main.py) já decodificou o MESMO token e guardou
    #    em request.state — reusa pra não pagar HMAC+parse duas vezes.
    payload = getattr(request.state, "jwt_payload", None)
    if payload is None:
        try:
            payload = decode_access_token(token)
        except JWTError:
            raise _credentials_exc

    # 2. ACESSO MARE NOSTRUM (impersonação): token com `imp` traz o superadmin
    #    em `sub` e o tenant do CLIENTE em `tid` — os dois divergem de propósito,
    #    então a checagem "usuário pertence ao tenant" não se aplica. Em troca,
    #    re-validamos a flag is_superadmin NO BANCO a cada request: se o super-
    #    acesso for revogado, o token vira inútil na hora (não espera expirar).
    if getattr(payload, "imp", False):
        user = (
            db.query(User)
            .filter(User.id == payload.sub, User.is_active.is_(True))
            .one_or_none()
        )
        if user is None or not getattr(user, "is_superadmin", False):
            raise _credentials_exc
        tenant = db.get(Tenant, payload.tid)
        if tenant is None:
            raise _credentials_exc
        return TenantContext(
            user_id=user.id,          # QUEM agiu (auditoria aponta pro superadmin)
            tenant_id=tenant.id,      # ONDE agiu (dados do cliente visitado)
            role="owner",             # enxerga tudo do cliente
            db=db,
            user_name=f"{user.full_name} (Mare Nostrum)",
            # Sem restrição de área e sem gate de billing: o dono do produto
            # precisa conseguir entrar até numa conta suspensa pra dar suporte.
            analytics_enabled=True, panel_enabled=True, map_enabled=True,
            demands_enabled=True, agenda_enabled=True, census_enabled=True,
            subscription_active=True,
            is_impersonating=True,
        )

    #    Confirma que o usuario do token ainda existe e pertence ao mesmo tenant.
    #    Esta dupla checagem (tid do token + tenant_id da linha) impede que
    #    um token "remixado" ou um usuario migrado entre tenants seja usado.
    #    JOIN com Tenant na MESMA query: o gate de assinatura precisa do tenant
    #    e 1 round-trip por request é mais barato que 2 (VPS de 1 vCPU).
    row = (
        db.query(User, Tenant)
        .join(Tenant, Tenant.id == User.tenant_id)
        .filter(
            User.id == payload.sub,
            User.tenant_id == payload.tid,
            User.is_active.is_(True),
        )
        .one_or_none()
    )
    if row is None:
        raise _credentials_exc
    user, tenant = row

    # 3. Gate de assinatura (billing Asaas). Tenants legados ficam 'active' e
    #    passam. Rotas de billing/identidade são isentas pra a tela de
    #    pagamento conseguir carregar.
    blocked = _subscription_blocks(tenant, datetime.now(timezone.utc))
    if blocked and not _is_billing_exempt(request.url.path):
        raise _payment_required_exc

    return TenantContext(
        user_id=user.id,
        tenant_id=user.tenant_id,
        subscription_active=not blocked,
        # Papel SEMPRE do BANCO, nunca do claim do JWT: com role=payload.role,
        # rebaixar um usuário (demote) não valia na prática — o token de 7 dias
        # (renovado em silêncio pelo /auth/me) perpetuava o papel antigo
        # indefinidamente. A linha User já está carregada; custo zero.
        role=user.role.value if hasattr(user.role, "value") else str(user.role),
        db=db,
        user_name=user.full_name,
        analytics_enabled=bool(getattr(user, "analytics_enabled", True)),
        panel_enabled=bool(getattr(user, "panel_enabled", True)),
        map_enabled=bool(getattr(user, "map_enabled", True)),
        demands_enabled=bool(getattr(user, "demands_enabled", True)),
        agenda_enabled=bool(getattr(user, "agenda_enabled", True)),
        census_enabled=bool(getattr(user, "census_enabled", False)),
    )


# Bearer OPCIONAL: quando a requisicao vem com chave de API nao existe token,
# e o esquema obrigatorio recusaria antes de olharmos a chave.
_oauth2_opcional = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login", auto_error=False
)


def get_context_flex(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    api_ctx: Annotated[TenantContext | None, Depends(get_context_by_api_key)] = None,
    token: Annotated[str | None, Depends(_oauth2_opcional)] = None,
) -> TenantContext:
    """Aceita chave de API OU login humano, nesta ordem.

    As duas devolvem o mesmo TenantContext, entao o resto do sistema nao
    precisa saber por onde a requisicao entrou — e nao ha um segundo caminho
    de autorizacao que possa divergir do primeiro com o tempo.
    """
    if api_ctx is not None:
        return api_ctx
    if not token:
        raise _credentials_exc
    return get_tenant_context(request=request, token=token, db=db)


# Alias tipado pronto para uso nas rotas: `ctx: CurrentTenant`
CurrentTenant = Annotated[TenantContext, Depends(get_context_flex)]


_area_forbidden = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Seu acesso a esta área foi desativado pelo responsável da campanha.",
)


def require_area(attr: str):
    """
    Dependência de rota: 403 se o usuário (que NÃO é owner) tiver o acesso
    daquela área desligado. O owner sempre passa. `attr` é o nome do flag no
    TenantContext (ex.: "demands_enabled"). Usado via
    `dependencies=[Depends(require_area("demands_enabled"))]` no include_router.
    """

    def _dep(ctx: CurrentTenant) -> None:
        if ctx.role != "owner" and not getattr(ctx, attr, True):
            raise _area_forbidden

    return _dep
