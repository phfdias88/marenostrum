"""Schemas de autenticacao."""
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """
    Login multi-tenant: o usuario informa em qual tenant esta entrando.
    Mesmo email pode existir em tenants diferentes (eleicoes distintas).
    """
    tenant_slug: str = Field(..., min_length=1, max_length=60)
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int            # segundos
    user_id: UUID
    tenant_id: UUID
    role: str


class MeResponse(BaseModel):
    """
    Dados do usuario logado. Usado pelo frontend para:
    (a) provar que o JWT foi aceito,
    (b) confirmar que o tenant_id do token bate com a sessao,
    (c) exibir nome/avatar/role no header.
    """
    user_id: UUID
    email: str
    full_name: str
    role: str
    tenant_id: UUID
    tenant_slug: str
    tenant_name: str
