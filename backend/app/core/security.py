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
    # ACESSO MARE NOSTRUM (impersonação): quando true, `sub` é o superadmin e
    # `tid` é o tenant do CLIENTE sendo visitado — os dois divergem de propósito.
    # Só a rota /admin/tenants/{id}/impersonate emite tokens assim, e o
    # get_tenant_context re-valida a flag is_superadmin no banco a cada request.
    imp: bool = False


class SetPasswordTokenPayload(BaseModel):
    """Token de definição de senha do owner recém-provisionado (uso único)."""
    sub: UUID        # user_id
    tid: UUID        # tenant_id
    slug: str        # tenant_slug (o link/e-mail carrega, o front precisa pra logar)
    purpose: str     # sempre "set_password"
    fp: str          # fingerprint da senha atual — invalida o token após 1 uso
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
    not_after: datetime | None = None,
    impersonated: bool = False,
) -> str:
    """Emite JWT assinado com HS256 contendo user_id + tenant_id + role.

    `not_after` é um TETO ABSOLUTO de expiração (acesso temporário): o `exp` do
    token nunca ultrapassa esse instante. Garante, com precisão, que o JWT de um
    trial não vive além do `expires_at` do banco — mesmo que o `expires_delta`
    (relativo) resultasse alguns ms depois por diferença de relógio.
    """
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        or timedelta(minutes=_settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    if not_after is not None:
        cap = _as_utc(not_after)
        if cap < expire:
            expire = cap
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "tid": str(tenant_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if impersonated:
        payload["imp"] = True
    return jwt.encode(
        payload,
        _settings.JWT_SECRET_KEY,
        algorithm=_settings.JWT_ALGORITHM,
    )


def _as_utc(dt: datetime | None) -> datetime | None:
    """Coage um datetime pra aware-UTC. Necessário cross-DB: o Postgres devolve
    timestamptz aware, mas o SQLite (testes) devolve naive — comparar naive com
    aware levanta TypeError."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def capped_token_delta(
    expires_at: datetime | None,
    now: datetime,
    default_delta: timedelta,
) -> timedelta | None:
    """TTL do JWT respeitando o acesso temporário (trial).

    - Sem `expires_at` (usuário normal): usa o TTL padrão.
    - Com `expires_at`: o token NUNCA vive além dele → min(padrão, restante).
    - Já expirou: devolve None (o caller não deve emitir/renovar o token).

    Usado no login E no refresh da sessão deslizante — sem o cap no refresh,
    um trial ganharia um token de 7 dias novo a cada /me, furando o limite.
    """
    exp = _as_utc(expires_at)
    if exp is None:
        return default_delta
    remaining = exp - now
    if remaining <= timedelta(0):
        return None
    return min(default_delta, remaining)


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


# ------------------------- Token de definição de senha ----------------------
# Enviado por e-mail ao owner recém-provisionado por uma compra. USO ÚNICO: o
# `fp` (fingerprint da senha atual) é conferido no consumo; assim que a senha
# muda, o fingerprint muda e o token vira inválido. Expira em horas.

def password_fingerprint(hashed_password: str) -> str:
    """Impressão curta da senha atual — muda quando a senha muda (uso único)."""
    return hashlib.sha256(hashed_password.encode("utf-8")).hexdigest()[:16]


def create_set_password_token(
    *,
    user_id: UUID,
    tenant_id: UUID,
    tenant_slug: str,
    fingerprint: str,
    expires_hours: int = 72,
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "tid": str(tenant_id),
        "slug": tenant_slug,
        "purpose": "set_password",
        "fp": fingerprint,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=expires_hours)).timestamp()),
    }
    return jwt.encode(payload, _settings.JWT_SECRET_KEY, algorithm=_settings.JWT_ALGORITHM)


def decode_set_password_token(token: str) -> SetPasswordTokenPayload:
    """Levanta JWTError se inválido/expirado/propósito errado."""
    raw = jwt.decode(token, _settings.JWT_SECRET_KEY, algorithms=[_settings.JWT_ALGORITHM])
    payload = SetPasswordTokenPayload(**raw)
    if payload.purpose != "set_password":
        raise JWTError("purpose inválido")
    return payload
