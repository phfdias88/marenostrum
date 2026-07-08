"""Schemas de autenticacao."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# ---------------------------------------------------------------------------
# Politica de senha (aplicada a senhas NOVAS: troca e definicao pelo admin).
# Nao se aplica ao LOGIN — la aceitamos qualquer coisa pra nao vazar a politica
# nem travar quem ja tem senha antiga.
# ---------------------------------------------------------------------------
PASSWORD_MIN_LENGTH = 10

# Senhas obvias barradas independentemente do tamanho. Inclui as que ja
# vazaram em defaults/exemplos do proprio projeto.
_PASSWORD_DENYLIST = {
    "senha123456", "1234567890", "12345678", "123456789", "senha12345",
    "password", "password1", "qwertyuiop", "mudeess@senha123",
    "senhab@123456", "marenostrum", "eleitoai", "admin12345",
}
# Substrings que, se dominarem a senha, indicam senha fraca/previsivel.
_PASSWORD_WEAK_SUBSTRINGS = ("marenostrum", "eleitoai")


def validate_password_strength(value: str) -> str:
    """
    Regras minimas p/ senha nova. Levanta ValueError (Pydantic -> 422) com
    mensagem amigavel em PT-BR quando reprovada.
    """
    v = (value or "").strip()
    if len(v) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"A senha deve ter pelo menos {PASSWORD_MIN_LENGTH} caracteres.")
    low = v.lower()
    if low in _PASSWORD_DENYLIST:
        raise ValueError("Essa senha é muito comum. Escolha uma senha mais forte.")
    if low.isdigit():
        raise ValueError("A senha não pode ser só números.")
    if any(s in low for s in _PASSWORD_WEAK_SUBSTRINGS):
        raise ValueError("A senha não pode conter o nome do sistema.")
    return v


class ChangePasswordRequest(BaseModel):
    """Troca de senha pelo próprio usuário autenticado."""
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=PASSWORD_MIN_LENGTH, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _check_new_password(cls, v: str) -> str:
        return validate_password_strength(v)


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
                "password": "sua-senha-aqui",
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
    # Super-acesso Mare Nostrum (auditoria cross-tenant). Default false.
    is_superadmin: bool = False
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
    """Admin define uma senha específica pra um membro."""
    password: str = Field(..., min_length=PASSWORD_MIN_LENGTH, max_length=128)

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        return validate_password_strength(v)


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
