"""Schemas Pydantic para a API de contatos."""
import re
from datetime import date, datetime
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.contact import ContactType

T = TypeVar("T")


# --------------------------------------------------- helpers de tag

# Tags: lowercase, sem espaco, sem acento, ate' 32 chars. Normalizamos no
# servidor pra evitar "Doador" vs "doador" virarem 2 segmentos diferentes.
_TAG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
_MAX_TAGS = 16


def _normalize_tag(t: str) -> str:
    """Lowercase + espaco/acento -> '-'. Devolve string vazia se invalida."""
    import unicodedata

    s = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")
    s = s.strip().lower().replace(" ", "-")
    # Mantem apenas chars validos pra slug
    s = re.sub(r"[^a-z0-9_-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def _validate_tags(value: list[str] | None) -> list[str]:
    """Normaliza, dedup mantendo ordem, valida regex, trunca em _MAX_TAGS."""
    if not value:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in value:
        norm = _normalize_tag(raw)
        if not norm or not _TAG_RE.match(norm):
            continue
        if norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
        if len(out) >= _MAX_TAGS:
            break
    return out


# ---------------------------------------------------------------- Base shapes


class ContactBase(BaseModel):
    """Campos comuns entre Create e Update. Apenas validacao — sem tenant_id."""
    full_name: str = Field(..., min_length=2, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=30)
    whatsapp: str | None = Field(None, max_length=30)
    instagram: str | None = Field(None, max_length=120)
    facebook: str | None = Field(None, max_length=200)

    cep: str | None = Field(None, max_length=9)
    address: str | None = Field(None, max_length=255)
    neighborhood: str | None = Field(None, max_length=100)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, min_length=2, max_length=2)
    voting_place: str | None = Field(None, max_length=200)

    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)

    birth_date: date | None = None

    type: ContactType = ContactType.VOTER
    notes: str | None = Field(None, max_length=1000)

    # Tags livres pra segmentacao. Sempre normalizadas no servidor.
    # Ate' 16 por contato. Cada tag: lowercase, [a-z0-9_-], 1-32 chars.
    tags: list[str] = Field(default_factory=list, max_length=64)

    @field_validator("tags", mode="before")
    @classmethod
    def _coerce_tags(cls, v):
        return _validate_tags(v if isinstance(v, list) else [])


class ContactCreate(ContactBase):
    """POST /contacts. tenant_id NUNCA vem do cliente — vem do JWT."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "full_name": "João da Silva",
                "phone": "(32) 99999-1234",
                "email": "joao@exemplo.com",
                "address": "Rua das Flores, 100",
                "neighborhood": "Centro",
                "city": "Juiz de Fora",
                "state": "MG",
                "birth_date": "1980-03-15",
                "type": "voter",
                "notes": "Liderança comunitária do bairro",
            }
        }
    )


class ContactUpdate(BaseModel):
    """
    PUT /contacts/{id}: todos os campos opcionais (partial update).
    `model_dump(exclude_unset=True)` no service garante que so atualiza o
    que veio explicitamente — campos omitidos mantem o valor atual.
    """
    full_name: str | None = Field(None, min_length=2, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=30)
    whatsapp: str | None = Field(None, max_length=30)
    instagram: str | None = Field(None, max_length=120)
    facebook: str | None = Field(None, max_length=200)
    cep: str | None = Field(None, max_length=9)
    address: str | None = Field(None, max_length=255)
    neighborhood: str | None = Field(None, max_length=100)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, min_length=2, max_length=2)
    voting_place: str | None = Field(None, max_length=200)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    birth_date: date | None = None
    type: ContactType | None = None
    notes: str | None = Field(None, max_length=1000)
    tags: list[str] | None = Field(None, max_length=64)

    @field_validator("tags", mode="before")
    @classmethod
    def _coerce_tags_update(cls, v):
        if v is None:
            return None
        return _validate_tags(v if isinstance(v, list) else [])


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


# --------------------------------------------------- Tags & Birthdays


class TagItem(BaseModel):
    """Tag + quantos contatos usam — pra chips/autocomplete no frontend."""
    tag: str
    count: int


class BirthdayContact(BaseModel):
    """
    Contato com aniversario no periodo (hoje / semana / mes).
    `days_until` = 0 (hoje), 1..N (proximos), nunca negativo.
    `age_turning` = idade que completara no aniversario (None se ano desconhecido).
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    phone: str | None = None
    email: EmailStr | None = None
    birth_date: date
    days_until: int
    age_turning: int | None = None
    tags: list[str] = Field(default_factory=list)
