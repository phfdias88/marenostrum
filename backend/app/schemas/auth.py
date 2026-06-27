"""Schemas de autenticacao."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ChangePasswordRequest(BaseModel):
    """Troca de senha pelo próprio usuário autenticado."""
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    """
    Login multi-tenant: o usuario informa em qual tenant esta entrando.
    Mesmo email pode existir em tenants diferentes (eleicoes distintas).
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tenant_slug": "marenostrum-admin",
                "email": "admin@marenostrum.com.br",
                "password": "MudeEss@Senha123",
            }
        }
    )

    tenant_slug: str = Field(
        ...,
        min_length=1,
        max_length=60,
        description="Apelido único da campanha (`marenostrum-admin`, `candidato-joao-2026`...)",
        examples=["marenostrum-admin"],
    )
    email: EmailStr = Field(
        ...,
        description="Email do usuário. Mesmo email pode existir em tenants diferentes.",
        examples=["admin@marenostrum.com.br"],
    )
    password: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Senha em texto puro (TLS protege em trânsito).",
    )


class TokenResponse(BaseModel):
    """JWT + metadados do usuário/tenant — retornado por POST /auth/login."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 3600,
                "user_id": "8a7b6c5d-1234-5678-9abc-def012345678",
                "tenant_id": "1234abcd-5678-90ef-1234-567890abcdef",
                "role": "owner",
            }
        }
    )

    access_token: str = Field(
        ..., description="JWT a ser enviado em `Authorization: Bearer <token>`",
    )
    token_type: str = "bearer"
    expires_in: int = Field(
        ..., description="Segundos até expirar (default 604800 = 7 dias)",
    )
    user_id: UUID
    tenant_id: UUID
    role: str = Field(..., examples=["owner", "manager", "staff", "volunteer"])


class MeResponse(BaseModel):
    """
    Dados do usuario logado + tenant. Usado pelo frontend pra:
    (a) provar que o JWT foi aceito,
    (b) confirmar que o tenant_id do token bate com a sessao,
    (c) exibir nome/role/tenant no header.
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": "8a7b6c5d-1234-5678-9abc-def012345678",
                "email": "admin@marenostrum.com.br",
                "full_name": "Administrador",
                "role": "owner",
                "tenant_id": "1234abcd-5678-90ef-1234-567890abcdef",
                "tenant_slug": "marenostrum-admin",
                "tenant_name": "MareNostrum Admin",
            }
        }
    )

    user_id: UUID
    email: str
    full_name: str
    role: str
    tenant_id: UUID
    tenant_slug: str
    tenant_name: str
    census_enabled: bool = False
    # Acesso por área (configurável pelo owner). Default amplo.
    analytics_enabled: bool = True
    panel_enabled: bool = True
    map_enabled: bool = True
    demands_enabled: bool = True
    agenda_enabled: bool = True
    # Sessão deslizante: quando o token atual passa da metade da validade,
    # /me devolve um novo aqui e o frontend troca o cookie em silêncio —
    # quem usa o sistema regularmente nunca é derrubado pro /login.
    refreshed_token: str | None = None
    refreshed_expires_in: int | None = None


# ---------------------------------------------------- Team management


TeamRole = Literal["manager", "staff", "volunteer"]

# Papéis que o owner pode ATRIBUIR a um membro existente (inclui owner =
# "Administrador / Dono", que dá acesso total + gestão da equipe).
AssignableRole = Literal["owner", "manager", "staff", "volunteer"]


class ChangeRoleRequest(BaseModel):
    """Troca o papel de um membro (apenas owner)."""
    role: AssignableRole


class SetPasswordRequest(BaseModel):
    """Admin define uma senha específica pra um membro (mín. 8 caracteres)."""
    password: str = Field(..., min_length=8, max_length=128)


class CreateUserRequest(BaseModel):
    """Criacao de novo membro da equipe (only owner)."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "coordenador@campanha.com.br",
                "full_name": "Maria Souza",
                "role": "manager",
            }
        }
    )

    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=150)
    role: TeamRole = "staff"


class CreateUserResponse(BaseModel):
    """Resposta com a senha temporaria — exibida UMA UNICA VEZ no frontend."""
    id: UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    temp_password: str = Field(
        ..., description="Senha temporaria gerada — mostre UMA vez ao admin.",
    )


class UserListItem(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    census_enabled: bool = False
    analytics_enabled: bool = True
    panel_enabled: bool = True
    map_enabled: bool = True
    demands_enabled: bool = True
    agenda_enabled: bool = True
    created_at: datetime


class CensusFlagRequest(BaseModel):
    """Liga/desliga o módulo Censo para um membro."""
    enabled: bool


# Áreas configuráveis pelo owner por usuário (acesso a seções do painel).
AccessArea = Literal["analytics", "panel", "map", "demands", "agenda", "census"]


class AccessFlagRequest(BaseModel):
    """Liga/desliga o acesso de um membro a uma área do painel."""
    area: AccessArea
    enabled: bool
