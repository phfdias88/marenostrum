"""Controller de autenticacao."""
import secrets
import string
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.utils.rate_limit import limiter

from app.core.database import get_db
from app.core.dependencies import CurrentTenant, oauth2_scheme
from app.core.errors import DomainError, NotFoundError, UnauthorizedError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models.user import User, UserRole
from app.schemas.auth import (
    AccessFlagRequest,
    CensusFlagRequest,
    ChangeRoleRequest,
    SetPasswordRequest,
    ChangePasswordRequest,
    CreateUserRequest,
    CreateUserResponse,
    LoginRequest,
    MeResponse,
    TokenResponse,
    UserListItem,
)
from app.services.auth import AuthService


class _ForbiddenError(DomainError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class _ConflictError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


def _require_owner(ctx: CurrentTenant) -> None:
    if ctx.role != "owner":
        raise _ForbiddenError("Apenas o dono da campanha pode gerenciar a equipe.")


def _require_team_admin(ctx: CurrentTenant) -> None:
    """
    Owner, Coordenador e Equipe podem GERENCIAR LIDERANÇAS (criar login só do
    formulário). A própria liderança (volunteer) não — já bloqueada pelo
    middleware, mas reforçamos aqui (defesa em profundidade).
    """
    if ctx.role not in ("owner", "manager", "staff"):
        raise _ForbiddenError("Você não tem acesso ao gerenciamento de equipe.")


def _require_can_manage(ctx: CurrentTenant, target: "User") -> None:
    """
    Quem não é Dono só pode mexer em LIDERANÇA (volunteer) — impede que
    Coordenador/Equipe criem ou alterem Dono/Coordenador/Equipe (escalonamento).
    """
    if ctx.role != "owner" and target.role != UserRole.VOLUNTEER:
        raise _ForbiddenError(
            "Você só pode gerenciar lideranças (acesso ao formulário)."
        )


# Charset sem caracteres ambiguous (0/O, 1/l/I).
_TEMP_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789@#%&"


def _gen_temp_password(n: int = 12) -> str:
    # secrets.choice = CSPRNG. Garante 1 maiuscula + 1 minuscula + 1 digito + 1 simbolo.
    while True:
        pw = "".join(secrets.choice(_TEMP_CHARS) for _ in range(n))
        if (
            any(c.isupper() for c in pw)
            and any(c.islower() for c in pw)
            and any(c.isdigit() for c in pw)
            and any(c in "@#%&" for c in pw)
        ):
            return pw


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Autenticar e receber JWT",
    description="""\
Emite um **JWT** vinculado ao tenant (`tid`) e ao usuário (`sub`).

### Fluxo
1. Informe `tenant_slug` (apelido único da campanha), `email` e `password`
2. Backend valida em **constant-time** (anti timing-attack)
3. Sucesso → retorna `access_token` válido por 7 dias (renovado em
   silêncio pelo `/auth/me` enquanto o usuário estiver ativo)

### Erros
- **401** — credenciais inválidas. Mensagem **sempre genérica**
  (`"Credenciais invalidas"`), por design — anti user-enumeration.
  Não distinguimos "email errado" de "senha errada" nem de "tenant inexistente".

### Como usar o token retornado
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```
""",
    responses={
        200: {"description": "Login bem-sucedido"},
        401: {
            "description": "Credenciais inválidas (mensagem genérica)",
            "content": {"application/json": {"example": {
                "code": "unauthorized",
                "message": "Credenciais invalidas",
            }}},
        },
    },
)
@limiter.limit("10/minute")
def login(
    request: Request,
    payload: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    # 10/min por IP — protege contra brute force de senha sem
    # incomodar quem digita errado 2-3x.
    return AuthService(db).login(payload)


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Dados do usuário autenticado",
    description="""\
Retorna o **usuário** e **tenant** associados ao JWT enviado.

Útil para:
- Provar ponta-a-ponta que o JWT foi aceito
- Confirmar que o `tenant_id` do token bate com o registro no DB
- Exibir nome/role/avatar no header do frontend

### Defesa em profundidade
Mesmo com JWT válido (assinatura ok), o backend **re-valida no banco** que:
- O usuário ainda existe e está ativo
- O `tenant_id` do token bate com o `tenant_id` do usuário no DB

Isso protege contra tokens forjados com `tid` arbitrário.
""",
)
def me(
    ctx: CurrentTenant,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> MeResponse:
    resp = AuthService.me(ctx)

    # Sessão deslizante: o frontend chama /me a cada carga do dashboard.
    # Se o token já passou da metade da validade, devolvemos um novo junto
    # e o cookie é trocado em silêncio — usuário ativo nunca cai no /login.
    # Token roubado continua limitado: renovar exige um token ainda válido.
    try:
        payload = decode_access_token(token)
        from datetime import datetime, timezone

        from app.config import get_settings

        ttl = get_settings().JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
        remaining = payload.exp - int(datetime.now(timezone.utc).timestamp())
        if 0 < remaining < ttl / 2:
            resp.refreshed_token = create_access_token(
                user_id=ctx.user_id, tenant_id=ctx.tenant_id, role=ctx.role,
            )
            resp.refreshed_expires_in = ttl
    except Exception:  # noqa: BLE001 — renovação é best-effort, nunca quebra /me
        pass
    return resp


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Trocar senha (usuário autenticado)",
    description="Verifica a senha atual e grava a nova (mín. 8 caracteres).",
)
def change_password(
    payload: ChangePasswordRequest,
    ctx: CurrentTenant,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    user = db.get(User, ctx.user_id)
    if user is None or not verify_password(payload.current_password, user.hashed_password):
        raise UnauthorizedError("Senha atual incorreta")
    user.hashed_password = hash_password(payload.new_password)
    db.commit()


# ============================================================ TEAM


@router.get(
    "/users",
    response_model=list[UserListItem],
    summary="Listar membros da equipe (apenas owner)",
)
def list_users(
    ctx: CurrentTenant,
    db: Annotated[Session, Depends(get_db)],
) -> list[UserListItem]:
    _require_team_admin(ctx)
    stmt = select(User).where(User.tenant_id == ctx.tenant_id)
    # Coordenador/Equipe só enxergam as LIDERANÇAS (não a equipe inteira).
    if ctx.role != "owner":
        stmt = stmt.where(User.role == UserRole.VOLUNTEER)
    rows = db.execute(stmt.order_by(User.created_at)).scalars().all()
    return [
        UserListItem(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=u.role.value if hasattr(u.role, "value") else str(u.role),
            is_active=u.is_active,
            census_enabled=bool(getattr(u, "census_enabled", False)),
            analytics_enabled=bool(getattr(u, "analytics_enabled", True)),
            panel_enabled=bool(getattr(u, "panel_enabled", True)),
            map_enabled=bool(getattr(u, "map_enabled", True)),
            demands_enabled=bool(getattr(u, "demands_enabled", True)),
            agenda_enabled=bool(getattr(u, "agenda_enabled", True)),
            created_at=u.created_at,
        )
        for u in rows
    ]


@router.post(
    "/users",
    response_model=CreateUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar novo membro (apenas owner)",
    description="""\
Cria um usuario na mesma campanha. Gera senha temporaria forte (12 chars,
mistura de maiusculas/minusculas/digitos/simbolos, sem caracteres ambiguos).

A senha temporaria volta NO BODY UMA UNICA VEZ. O backend nao armazena em
texto puro — depois disso, so o hash. Mostre pro admin, copie pra um cofre
de senhas (ou WhatsApp/email da pessoa), e oriente trocar no 1o login.

### Erros
- **403** se quem chama nao for owner.
- **409** se ja existir usuario com o mesmo email nesta campanha.
""",
)
@limiter.limit("10/minute")
def create_user(
    request: Request,
    payload: CreateUserRequest,
    ctx: CurrentTenant,
    db: Annotated[Session, Depends(get_db)],
) -> CreateUserResponse:
    _require_team_admin(ctx)
    # Coordenador/Equipe só podem cadastrar LIDERANÇA (acesso ao formulário).
    # Só o Dono cria outros papéis — impede escalonamento de privilégio.
    if ctx.role != "owner" and payload.role != "volunteer":
        raise _ForbiddenError(
            "Você só pode cadastrar lideranças (acesso ao formulário)."
        )

    # Email unico por tenant.
    existing = db.execute(
        select(User).where(
            User.tenant_id == ctx.tenant_id,
            User.email == payload.email.lower(),
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise _ConflictError("Ja existe um usuario com esse email nesta campanha.")

    temp = _gen_temp_password()
    role_enum = UserRole(payload.role)  # validates against enum values
    user = User(
        tenant_id=ctx.tenant_id,
        email=payload.email.lower(),
        full_name=payload.full_name.strip(),
        hashed_password=hash_password(temp),
        role=role_enum,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return CreateUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
        is_active=user.is_active,
        temp_password=temp,
    )


@router.post(
    "/users/{user_id}/reset-password",
    response_model=CreateUserResponse,
    summary="Gerar nova senha temporaria pra um membro (owner)",
    description="Gera nova temp_password e devolve UMA vez. Use quando a pessoa esquecer a senha.",
)
def reset_user_password(
    user_id: UUID,
    ctx: CurrentTenant,
    db: Annotated[Session, Depends(get_db)],
) -> CreateUserResponse:
    _require_team_admin(ctx)
    user = db.execute(
        select(User).where(User.id == user_id, User.tenant_id == ctx.tenant_id)
    ).scalar_one_or_none()
    if user is None:
        raise NotFoundError("Usuario nao encontrado.")
    _require_can_manage(ctx, user)
    if user.role == UserRole.OWNER and user.id != ctx.user_id:
        raise _ForbiddenError("Nao da pra resetar senha de outro owner.")

    temp = _gen_temp_password()
    user.hashed_password = hash_password(temp)
    db.commit()
    return CreateUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
        is_active=user.is_active,
        temp_password=temp,
    )


@router.post(
    "/users/{user_id}/deactivate",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desativar membro (owner)",
    description="Sessoes futuras sao bloqueadas. Nao apaga dados; reativacao manual via DB.",
)
def deactivate_user(
    user_id: UUID,
    ctx: CurrentTenant,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    _require_team_admin(ctx)
    if user_id == ctx.user_id:
        raise _ForbiddenError("Voce nao pode desativar a propria conta.")
    user = db.execute(
        select(User).where(User.id == user_id, User.tenant_id == ctx.tenant_id)
    ).scalar_one_or_none()
    if user is None:
        raise NotFoundError("Usuario nao encontrado.")
    _require_can_manage(ctx, user)
    if user.role == UserRole.OWNER:
        raise _ForbiddenError("Nao da pra desativar outro owner.")
    user.is_active = False
    db.commit()


@router.post(
    "/users/{user_id}/reactivate",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reativar membro (owner)",
)
def reactivate_user(
    user_id: UUID,
    ctx: CurrentTenant,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    _require_team_admin(ctx)
    user = db.execute(
        select(User).where(User.id == user_id, User.tenant_id == ctx.tenant_id)
    ).scalar_one_or_none()
    if user is None:
        raise NotFoundError("Usuario nao encontrado.")
    _require_can_manage(ctx, user)
    user.is_active = True
    db.commit()


@router.post(
    "/users/{user_id}/census",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Liberar/bloquear o módulo Censo para um membro (owner)",
    description="Liga/desliga o feature-flag census_enabled do usuário.",
)
def set_census_flag(
    user_id: UUID,
    payload: CensusFlagRequest,
    ctx: CurrentTenant,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    _require_owner(ctx)
    user = db.execute(
        select(User).where(User.id == user_id, User.tenant_id == ctx.tenant_id)
    ).scalar_one_or_none()
    if user is None:
        raise NotFoundError("Usuario nao encontrado.")
    user.census_enabled = bool(payload.enabled)
    db.commit()


# Áreas configuráveis → coluna no modelo User.
_ACCESS_COLUMN = {
    "analytics": "analytics_enabled",
    "panel": "panel_enabled",
    "map": "map_enabled",
    "demands": "demands_enabled",
    "agenda": "agenda_enabled",
    "census": "census_enabled",
}


@router.post(
    "/users/{user_id}/access",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Liberar/bloquear o acesso de um membro a uma área (owner)",
    description=(
        "Liga/desliga, por usuário, o acesso a uma área do painel: "
        "analytics (Análises/TSE), panel (Painel), map (Mapa), demands "
        "(Demandas), agenda (Agenda) ou census (Censo). Só o owner controla."
    ),
)
def set_access_flag(
    user_id: UUID,
    payload: AccessFlagRequest,
    ctx: CurrentTenant,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    _require_owner(ctx)
    user = db.execute(
        select(User).where(User.id == user_id, User.tenant_id == ctx.tenant_id)
    ).scalar_one_or_none()
    if user is None:
        raise NotFoundError("Usuario nao encontrado.")
    setattr(user, _ACCESS_COLUMN[payload.area], bool(payload.enabled))
    db.commit()


@router.post(
    "/users/{user_id}/role",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mudar o papel de um membro (owner)",
    description=(
        "Promove/rebaixa um membro: owner (Administrador/Dono, acesso total + "
        "gerencia equipe), manager (Coordenador), staff (Equipe) ou volunteer "
        "(Liderança, só formulário). Só o owner pode, e não pode mudar o "
        "próprio papel (evita se trancar fora)."
    ),
)
def change_user_role(
    user_id: UUID,
    payload: ChangeRoleRequest,
    ctx: CurrentTenant,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    _require_owner(ctx)
    if user_id == ctx.user_id:
        raise _ForbiddenError("Voce nao pode mudar o proprio papel.")
    user = db.execute(
        select(User).where(User.id == user_id, User.tenant_id == ctx.tenant_id)
    ).scalar_one_or_none()
    if user is None:
        raise NotFoundError("Usuario nao encontrado.")
    user.role = UserRole(payload.role)
    db.commit()


@router.post(
    "/users/{user_id}/set-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Definir uma senha específica pra um membro (admin)",
    description=(
        "O admin DEFINE a senha do membro (mín. 8 caracteres) — diferente do "
        "/reset-password, que gera uma aleatória. Owner mexe em qualquer membro "
        "(menos outro owner); Coordenador/Equipe só em lideranças."
    ),
)
def set_user_password(
    user_id: UUID,
    payload: SetPasswordRequest,
    ctx: CurrentTenant,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    _require_team_admin(ctx)
    user = db.execute(
        select(User).where(User.id == user_id, User.tenant_id == ctx.tenant_id)
    ).scalar_one_or_none()
    if user is None:
        raise NotFoundError("Usuario nao encontrado.")
    _require_can_manage(ctx, user)
    if user.role == UserRole.OWNER and user.id != ctx.user_id:
        raise _ForbiddenError("Nao da pra definir senha de outro owner.")
    user.hashed_password = hash_password(payload.password)
    db.commit()


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir um membro de vez (admin)",
    description=(
        "Remove o usuário PERMANENTEMENTE (diferente de desativar). Os contatos "
        "que ele cadastrou continuam — o nome de quem cadastrou fica gravado, "
        "mas o vínculo (filtro por autor) é perdido. Não dá pra excluir a "
        "própria conta nem um Administrador (Dono): rebaixe o papel antes. "
        "Coordenador/Equipe só excluem lideranças."
    ),
)
def delete_user(
    user_id: UUID,
    ctx: CurrentTenant,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    _require_team_admin(ctx)
    if user_id == ctx.user_id:
        raise _ForbiddenError("Voce nao pode excluir a propria conta.")
    user = db.execute(
        select(User).where(User.id == user_id, User.tenant_id == ctx.tenant_id)
    ).scalar_one_or_none()
    if user is None:
        raise NotFoundError("Usuario nao encontrado.")
    _require_can_manage(ctx, user)
    if user.role == UserRole.OWNER:
        raise _ForbiddenError(
            "Nao da pra excluir um Administrador (Dono). Rebaixe o papel antes."
        )
    # FK contacts.created_by_user_id e' ON DELETE SET NULL — contatos ficam,
    # so perdem o vinculo de autor (o nome denormalizado permanece).
    db.delete(user)
    db.commit()
