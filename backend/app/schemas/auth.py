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
