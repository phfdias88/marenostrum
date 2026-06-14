"""
Dependencias FastAPI compartilhadas.

`get_tenant_context` e a porta de entrada das rotas autenticadas:
- valida o JWT (Authorization: Bearer ...)
- extrai user_id + tenant_id
- confere que o usuario ainda existe, esta ativo, e pertence ao tenant do token
- retorna um TenantContext com a sessao do DB ja aberta

Esta dependencia DEVE ser usada por TODA rota que toca dados de tenant.
"""
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.core.tenant_context import TenantContext
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


def get_tenant_context(
    token: Annotated[str, Depends(_oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> TenantContext:
    # 1. Decodifica o JWT (assinatura, expiracao, formato)
    try:
        payload = decode_access_token(token)
    except JWTError:
        raise _credentials_exc

    # 2. Confirma que o usuario do token ainda existe e pertence ao mesmo tenant.
    #    Esta dupla checagem (tid do token + tenant_id da linha) impede que
    #    um token "remixado" ou um usuario migrado entre tenants seja usado.
    user = (
        db.query(User)
        .filter(
            User.id == payload.sub,
            User.tenant_id == payload.tid,
            User.is_active.is_(True),
        )
        .one_or_none()
    )
    if user is None:
        raise _credentials_exc

    return TenantContext(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=payload.role,
        db=db,
    )


# Alias tipado pronto para uso nas rotas: `ctx: CurrentTenant`
CurrentTenant = Annotated[TenantContext, Depends(get_tenant_context)]
