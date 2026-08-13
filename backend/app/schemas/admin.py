"""
Schemas do Painel do Superadministrador (Mare Nostrum).

Operações CROSS-TENANT restritas a is_superadmin=true: listar todos os clientes,
criar conta de CORTESIA (titular sem pagamento) e administrar o perfil do titular
(resetar senha, ativar/desativar). Toda a proteção é feita no controller
(app/controllers/admin.py) — estes schemas só descrevem os payloads.
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.auth import validate_password_strength


class AdminTenantItem(BaseModel):
    """Um cliente (tenant) na visão do superadmin, com o titular resumido."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    is_active: bool
    subscription_status: str | None = None
    created_at: datetime | None = None
    user_count: int = 0
    # Titular da assinatura (is_account_owner). Pode ser None em tenant sem
    # titular marcado (legado) — a UI mostra "—".
    titular_user_id: UUID | None = None
    titular_email: str | None = None
    titular_name: str | None = None
    titular_active: bool | None = None
    # Acesso temporário do titular (cortesia com prazo). NULL = sem limite.
    # first_login_at NULL = relógio ainda não começou (aguardando o 1º login).
    titular_usage_limit_hours: float | None = None
    titular_first_login_at: datetime | None = None
    titular_expires_at: datetime | None = None
    # É uma conta de CORTESIA? (ativa, sem assinatura vinculada). Heurística
    # exibida como selo na UI; não é uma coluna do banco.
    is_courtesy: bool = False


class AdminTenantList(BaseModel):
    items: list[AdminTenantItem]
    total: int


class CreateCompAccountRequest(BaseModel):
    """Cria um cliente de CORTESIA: tenant + titular, sem pagamento."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Dr. João Águia",
                "email": "joao@campanha.com.br",
                "tenant_name": "Campanha João 2026",
                "usage_limit_hours": 48,
            }
        }
    )

    name: str = Field(..., min_length=2, max_length=150, description="Nome do titular.")
    email: EmailStr = Field(..., description="E-mail de login do titular.")
    tenant_name: str | None = Field(
        None, max_length=120,
        description="Nome da campanha/cliente. Se vazio, usa o nome do titular.",
    )
    # Acesso temporário (mesma regra do trial de equipe): o relógio só começa no
    # PRIMEIRO login do titular, e a partir dali corre absoluto até expirar.
    # None/0 = cortesia sem prazo. Aceita fração (2.5 = 2h30); teto de 1 ano.
    usage_limit_hours: float | None = Field(
        default=None, ge=0, le=8760,
        description=(
            "Horas de uso a partir do 1º login do titular. "
            "Vazio ou 0 = sem limite de tempo."
        ),
    )


class CreateCompAccountResponse(BaseModel):
    tenant_id: UUID
    tenant_slug: str
    user_id: UUID
    email: str
    # Senha provisória — mostrada UMA vez. O titular troca no 1º login.
    temp_password: str
    # Eco do prazo aplicado (None = sem limite). A UI confirma pro operador
    # o que foi de fato gravado.
    usage_limit_hours: float | None = None


class AdminResetPasswordResponse(BaseModel):
    temp_password: str


class ImpersonateResponse(BaseModel):
    """Token de ACESSO MARE NOSTRUM a um cliente ("entrar como").

    Sessão curta e separada: o frontend guarda o token do superadmin e volta
    pra ele ao sair. Todo acesso fica registrado na auditoria.
    """
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    tenant_id: UUID
    tenant_name: str
    tenant_slug: str


class AdminSetActiveRequest(BaseModel):
    is_active: bool


class AdminSetPasswordRequest(BaseModel):
    """Superadmin define uma senha específica pro titular (em vez de aleatória)."""
    password: str = Field(..., min_length=10, max_length=128)

    @field_validator("password")
    @classmethod
    def _check(cls, v: str) -> str:
        return validate_password_strength(v)
