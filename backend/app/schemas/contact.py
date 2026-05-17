"""Schemas Pydantic para a API de contatos."""
from datetime import date, datetime
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.contact import ContactType

T = TypeVar("T")


# ---------------------------------------------------------------- Base shapes


class ContactBase(BaseModel):
    """Campos comuns entre Create e Update. Apenas validacao — sem tenant_id."""
    full_name: str = Field(..., min_length=2, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=30)

    address: str | None = Field(None, max_length=255)
    neighborhood: str | None = Field(None, max_length=100)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, min_length=2, max_length=2)

    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)

    birth_date: date | None = None

    type: ContactType = ContactType.VOTER
    notes: str | None = Field(None, max_length=1000)


class ContactCreate(ContactBase):
    """POST /contacts. tenant_id NUNCA vem do cliente — vem do JWT."""


class ContactUpdate(BaseModel):
    """
    PUT /contacts/{id}: todos os campos opcionais (partial update).
    `model_dump(exclude_unset=True)` no service garante que so atualiza o
    que veio explicitamente — campos omitidos mantem o valor atual.
    """
    full_name: str | None = Field(None, min_length=2, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=30)
    address: str | None = Field(None, max_length=255)
    neighborhood: str | None = Field(None, max_length=100)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, min_length=2, max_length=2)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    birth_date: date | None = None
    type: ContactType | None = None
    notes: str | None = Field(None, max_length=1000)


class ContactRead(ContactBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------- Paginated response


class Page(BaseModel, Generic[T]):
    """
    Envelope padrao para listagens paginadas.
    O frontend (DataTable) usa `total` para calcular numero de paginas.
    """
    items: list[T]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------- CSV import


class ImportRowError(BaseModel):
    """Erro em uma linha especifica do CSV (1-indexed, header e linha 1)."""
    row: int
    message: str


class ImportResult(BaseModel):
    """Resposta de POST /contacts/import."""
    imported: int           # quantos foram efetivamente inseridos
    skipped: int            # quantos foram pulados (erros + duplicatas)
    total_rows: int         # total de linhas do CSV (excluindo header)
    errors: list[ImportRowError]  # truncado em 50 para nao explodir resposta
