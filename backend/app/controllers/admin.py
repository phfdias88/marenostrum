"""
Controller do Painel do Superadministrador (Mare Nostrum).

Operações CROSS-TENANT restritas a is_superadmin=true (flag setada só no banco):
- Listar todos os clientes (tenants) com o titular de cada um.
- Criar conta de CORTESIA: tenant + titular (is_account_owner=True), sem passar
  pelo billing — o titular loga e usa tudo, de graça.
- Administrar o perfil do titular de qualquer cliente: resetar/definir senha,
  ativar/desativar.

Esta é a ÚNICA porta que atravessa o isolamento multi-tenant pela API — por isso
o gate (require_superadmin) é uma DEPENDENCY em toda rota (roda antes do corpo),
e os alvos das ações administrativas são restritos a TITULARES
(is_account_owner), não a qualquer membro de qualquer tenant.
"""
import secrets
from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import CurrentTenant
from app.core.errors import DomainError, NotFoundError
from app.core.security import create_access_token, hash_password
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.schemas.admin import (
    AdminResetPasswordResponse,
    AdminSetActiveRequest,
    AdminSetPasswordRequest,
    AdminTenantItem,
    AdminTenantList,
    CreateCompAccountRequest,
    CreateCompAccountResponse,
    ImpersonateResponse,
)
from app.services.audit import record_audit
from app.services.provisioning import _unique_slug, slugify

router = APIRouter(prefix="/admin", tags=["admin (superadmin)"])


class _ForbiddenError(DomainError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class _ConflictError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


# Charset sem ambíguos (0/O, 1/l/I) — igual ao da equipe (auth.py). Replicado
# aqui pra não acoplar o admin ao caminho quente de autenticação.
_TEMP_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789@#%&"

# Sessão de "entrar como" é curta de propósito: acesso a dado de cliente não
# deve ficar aberto por dias. Renovar = clicar de novo (e auditar de novo).
IMPERSONATION_TTL_MINUTES = 60


def _gen_temp_password(n: int = 12) -> str:
    while True:
        pw = "".join(secrets.choice(_TEMP_CHARS) for _ in range(n))
        if (
            any(c.isupper() for c in pw)
            and any(c.islower() for c in pw)
            and any(c.isdigit() for c in pw)
            and any(c in "@#%&" for c in pw)
        ):
            return pw


def require_superadmin(
    ctx: CurrentTenant,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Gate ESTRITO como DEPENDENCY: roda ANTES do parsing do corpo, então
    quem não é superadmin toma 403 sem sequer ter o payload validado (não
    vaza schema nem 422 pra não-autorizado). Super-acesso é uma flag do banco
    (não papel/tenant); relemos o usuário e exigimos is_superadmin."""
    user = db.get(User, ctx.user_id)
    if user is None or not getattr(user, "is_superadmin", False):
        raise _ForbiddenError("Acesso restrito à equipe Mare Nostrum (super-admin).")
    return user


# Aplicado a TODAS as rotas do router (checagem única, antes do corpo).
_SUPERADMIN = Annotated[User, Depends(require_superadmin)]


def _load_titular_target(db: Session, user_id: UUID) -> User:
    """Carrega o usuário-alvo de uma ação administrativa e exige que seja um
    TITULAR (is_account_owner). Limita o alcance do painel: o superadmin
    administra titulares, não membros arbitrários de qualquer tenant."""
    target = db.get(User, user_id)
    if target is None:
        raise NotFoundError("Usuário não encontrado.")
    if not getattr(target, "is_account_owner", False):
        raise _ForbiddenError(
            "Esta ação só se aplica ao titular da assinatura do cliente."
        )
    return target


@router.get(
    "/tenants",
    response_model=AdminTenantList,
    summary="Listar TODOS os clientes (superadmin) com o titular de cada um",
)
def list_tenants(
    ctx: CurrentTenant,
    db: Annotated[Session, Depends(get_db)],
    _su: _SUPERADMIN,
) -> AdminTenantList:

    tenants = db.execute(select(Tenant).order_by(Tenant.created_at)).scalars().all()

    # Titular de cada tenant (is_account_owner) — 1 query, mapeada por tenant.
    titulares = {
        u.tenant_id: u
        for u in db.execute(
            select(User).where(User.is_account_owner.is_(True))
        ).scalars().all()
    }
    # Contagem de usuários por tenant — 1 query.
    counts = dict(
        db.execute(
            select(User.tenant_id, func.count()).group_by(User.tenant_id)
        ).all()
    )

    items: list[AdminTenantItem] = []
    for t in tenants:
        tit = titulares.get(t.id)
        st = getattr(t, "subscription_status", None)
        # Cortesia (heurística p/ selo): ativa e sem assinatura formal marcada.
        is_courtesy = bool(t.is_active) and st in (None, "active")
        items.append(
            AdminTenantItem(
                id=t.id,
                name=t.name,
                slug=t.slug,
                is_active=bool(t.is_active),
                subscription_status=st,
                created_at=getattr(t, "created_at", None),
                user_count=int(counts.get(t.id, 0)),
                titular_user_id=tit.id if tit else None,
                titular_email=tit.email if tit else None,
                titular_name=tit.full_name if tit else None,
                titular_active=bool(tit.is_active) if tit else None,
                titular_usage_limit_hours=(
                    getattr(tit, "usage_limit_hours", None) if tit else None
                ),
                titular_first_login_at=(
                    getattr(tit, "first_login_at", None) if tit else None
                ),
                titular_expires_at=(
                    getattr(tit, "expires_at", None) if tit else None
                ),
                is_courtesy=is_courtesy,
            )
        )
    return AdminTenantList(items=items, total=len(items))


@router.post(
    "/tenants",
    response_model=CreateCompAccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar conta de CORTESIA: tenant + titular, sem pagamento (superadmin)",
)
def create_comp_account(
    payload: CreateCompAccountRequest,
    ctx: CurrentTenant,
    db: Annotated[Session, Depends(get_db)],
    _su: _SUPERADMIN,
) -> CreateCompAccountResponse:

    email = payload.email.strip().lower()
    name = payload.name.strip()
    tenant_name = (payload.tenant_name or name).strip()[:120]

    # Colisão global de e-mail seria confusa no login multi-tenant só se no
    # MESMO tenant; aqui criamos tenant novo, então só barramos e-mail já usado
    # em algum tenant de forma idêntica de titular ativo (evita duplicar pessoa).
    existing_titular = db.execute(
        select(User).where(
            User.email == email, User.is_account_owner.is_(True)
        )
    ).scalar_one_or_none()
    if existing_titular is not None:
        raise _ConflictError(
            "Já existe um titular com esse e-mail. Use outro e-mail ou "
            "administre a conta existente."
        )

    tenant = Tenant(
        name=tenant_name,
        slug=_unique_slug(db, slugify(tenant_name)),
        is_active=True,
        subscription_status="active",  # cortesia: nunca bloqueia no gate
    )
    db.add(tenant)
    db.flush()

    # Acesso temporário: normaliza 0 → None (sem limite). O relógio NÃO começa
    # aqui — o AuthService materializa first_login_at/expires_at no 1º login
    # do titular (mesma regra do trial de equipe).
    _limit = payload.usage_limit_hours
    usage_limit = _limit if (_limit and _limit > 0) else None

    temp = _gen_temp_password()
    owner = User(
        tenant_id=tenant.id,
        email=email,
        full_name=name[:150],
        hashed_password=hash_password(temp),
        role=UserRole.OWNER,
        is_active=True,
        is_account_owner=True,  # é o TITULAR (mesmo sem pagamento)
        usage_limit_hours=usage_limit,
        # Pacote completo ligado.
        census_enabled=True,
        analytics_enabled=True,
        panel_enabled=True,
        map_enabled=True,
        demands_enabled=True,
        agenda_enabled=True,
    )
    db.add(owner)
    db.flush()
    record_audit(
        ctx,
        action="create",
        entity_type="tenant",
        entity_id=tenant.id,
        summary=(
            f"[superadmin] Criou conta de cortesia {tenant.slug} / titular {email}"
            + (f" · limite de {usage_limit}h de uso" if usage_limit else "")
        ),
    )
    db.commit()
    db.refresh(tenant)
    db.refresh(owner)

    return CreateCompAccountResponse(
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        user_id=owner.id,
        email=owner.email,
        temp_password=temp,
        usage_limit_hours=owner.usage_limit_hours,
    )


@router.post(
    "/tenants/{tenant_id}/impersonate",
    response_model=ImpersonateResponse,
    summary="ENTRAR COMO: abrir a conta de um cliente (superadmin)",
    description="""\
Emite uma sessão CURTA de acesso ao ambiente de um cliente — o dono do produto
enxerga os dados como o titular veria (contatos, demandas, mapas, análises).

Rastreabilidade: o token guarda a identidade REAL de quem entrou, então tudo o
que for feito lá dentro é registrado na auditoria como ação do superadmin, não
do cliente. O acesso em si também é registrado no momento da emissão.
""",
)
def impersonate_tenant(
    tenant_id: UUID,
    ctx: CurrentTenant,
    db: Annotated[Session, Depends(get_db)],
    _su: _SUPERADMIN,
) -> ImpersonateResponse:
    # Impersonação a partir de uma sessão já impersonada seria um salto em
    # cadeia difícil de auditar — exige sessão real do superadmin.
    if getattr(ctx, "is_impersonating", False):
        raise _ForbiddenError(
            "Saia do acesso atual antes de entrar em outro cliente."
        )

    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundError("Cliente não encontrado.")

    ttl = timedelta(minutes=IMPERSONATION_TTL_MINUTES)
    token = create_access_token(
        user_id=ctx.user_id,      # identidade REAL (superadmin)
        tenant_id=tenant.id,      # ambiente visitado (cliente)
        role="owner",
        expires_delta=ttl,
        impersonated=True,
    )
    record_audit(
        ctx,
        action="update",
        entity_type="tenant",
        entity_id=tenant.id,
        summary=(
            f"[superadmin] Acessou o ambiente do cliente {tenant.name} "
            f"({tenant.slug}) · sessão de {IMPERSONATION_TTL_MINUTES} min"
        ),
    )
    db.commit()

    return ImpersonateResponse(
        access_token=token,
        expires_in=int(ttl.total_seconds()),
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        tenant_slug=tenant.slug,
    )


@router.post(
    "/users/{user_id}/reset-password",
    response_model=AdminResetPasswordResponse,
    summary="Resetar a senha do titular de qualquer cliente (superadmin)",
)
def reset_titular_password(
    user_id: UUID,
    ctx: CurrentTenant,
    db: Annotated[Session, Depends(get_db)],
    _su: _SUPERADMIN,
) -> AdminResetPasswordResponse:
    target = _load_titular_target(db, user_id)
    temp = _gen_temp_password()
    target.hashed_password = hash_password(temp)
    record_audit(
        ctx,
        action="update",
        entity_type="user",
        entity_id=target.id,
        summary=f"[superadmin] Resetou a senha do titular {target.email}",
    )
    db.commit()
    return AdminResetPasswordResponse(temp_password=temp)


@router.post(
    "/users/{user_id}/set-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Definir uma senha específica pro titular (superadmin)",
)
def set_titular_password(
    user_id: UUID,
    payload: AdminSetPasswordRequest,
    ctx: CurrentTenant,
    db: Annotated[Session, Depends(get_db)],
    _su: _SUPERADMIN,
) -> None:
    target = _load_titular_target(db, user_id)
    target.hashed_password = hash_password(payload.password)
    record_audit(
        ctx,
        action="update",
        entity_type="user",
        entity_id=target.id,
        summary=f"[superadmin] Definiu nova senha para o titular {target.email}",
    )
    db.commit()


@router.post(
    "/users/{user_id}/set-active",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Ativar/desativar o titular de um cliente (superadmin)",
)
def set_titular_active(
    user_id: UUID,
    payload: AdminSetActiveRequest,
    ctx: CurrentTenant,
    db: Annotated[Session, Depends(get_db)],
    _su: _SUPERADMIN,
) -> None:
    if user_id == ctx.user_id:
        raise _ForbiddenError("Você não pode desativar a própria conta por aqui.")
    target = _load_titular_target(db, user_id)
    target.is_active = payload.is_active
    record_audit(
        ctx,
        action="update",
        entity_type="user",
        entity_id=target.id,
        summary=(
            f"[superadmin] {'Reativou' if payload.is_active else 'Desativou'} "
            f"o titular {target.email}"
        ),
    )
    db.commit()
