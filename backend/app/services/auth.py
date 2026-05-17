"""
Service de autenticacao.

Regra critica: mensagens de erro NUNCA revelam se foi "email errado",
"senha errada" ou "tenant inexistente" — sempre "credenciais invalidas".
Isso evita user enumeration.
"""
import structlog
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import UnauthorizedError
from app.core.security import create_access_token, hash_password, verify_password
from app.repositories.user import UserRepository
from app.schemas.auth import LoginRequest, TokenResponse

log = structlog.get_logger("marenostrum.services.auth")

# Hash "fantasma" usado quando o usuario nao existe, para que a duracao
# da resposta seja parecida com a do caso valido (mitiga timing attack).
_DUMMY_HASH = hash_password("dummy-password-for-constant-time")


class AuthService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._users = UserRepository(db)

    def login(self, payload: LoginRequest) -> TokenResponse:
        user = self._users.get_by_email_and_tenant_slug(
            email=payload.email,
            tenant_slug=payload.tenant_slug,
        )

        # Sempre executa verify_password para evitar timing leak
        valid_password = verify_password(
            payload.password,
            user.hashed_password if user else _DUMMY_HASH,
        )

        if user is None or not valid_password:
            log.info(
                "login_failed",
                tenant_slug=payload.tenant_slug,
                email=payload.email,
            )
            raise UnauthorizedError("Credenciais invalidas")

        settings = get_settings()
        token = create_access_token(
            user_id=user.id,
            tenant_id=user.tenant_id,
            role=user.role.value,
        )

        log.info(
            "login_success",
            user_id=str(user.id),
            tenant_id=str(user.tenant_id),
        )

        return TokenResponse(
            access_token=token,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user_id=user.id,
            tenant_id=user.tenant_id,
            role=user.role.value,
        )
