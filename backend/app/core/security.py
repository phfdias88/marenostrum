"""
Camada de seguranca: hash de senha + emissao/decodificacao de JWT.

O JWT carrega obrigatoriamente:
- sub: id do usuario (UUID, string)
- tid: tenant_id (UUID, string)  <-- chave do isolamento multi-tenant
- role: papel do usuario
- exp/iat: padrao JWT
"""
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import get_settings

_settings = get_settings()


class TokenPayload(BaseModel):
    """Forma tipada do payload decodificado do JWT."""
    sub: UUID        # user_id
    tid: UUID        # tenant_id
    role: str
    exp: int
    iat: int


# ----------------------------- Password hashing -----------------------------
# Bcrypt limita input a 72 bytes. Pre-hashamos com SHA256 + base64 para:
# (a) eliminar o limite mantendo entropia (padrao Django/Devise)
# (b) evitar leak: bcrypt processa 44 bytes de digest, nao a senha bruta.

def _prehash(plain: str) -> bytes:
    digest = hashlib.sha256(plain.encode("utf-8")).digest()
    return base64.b64encode(digest)  # 44 bytes, sempre < 72


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_prehash(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # Hash malformado no DB nao deve crashar o login — apenas nega.
        return False


# --------------------------------- JWT --------------------------------------

def create_access_token(
    *,
    user_id: UUID,
    tenant_id: UUID,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Emite JWT assinado com HS256 contendo user_id + tenant_id + role."""
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        or timedelta(minutes=_settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "tid": str(tenant_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(
        payload,
        _settings.JWT_SECRET_KEY,
        algorithm=_settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> TokenPayload:
    """Decodifica e valida o JWT. Levanta JWTError se invalido/expirado."""
    try:
        raw = jwt.decode(
            token,
            _settings.JWT_SECRET_KEY,
            algorithms=[_settings.JWT_ALGORITHM],
        )
    except JWTError:
        # Repassa para a camada de dependencia decidir o HTTP status
        raise
    return TokenPayload(**raw)
