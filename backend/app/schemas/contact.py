"""Schemas Pydantic para entrada/saida da API de contatos."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.contact import ContactType


class ContactCreate(BaseModel):
    """Payload aceito no POST /contacts. NUNCA inclui tenant_id - ele vem do JWT."""
    full_name: str = Field(..., min_length=2, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=30)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, min_length=2, max_length=2)
    type: ContactType = ContactType.VOTER
    notes: str | None = Field(None, max_length=1000)


class ContactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: str | None
    phone: str | None
    city: str | None
    state: str | None
    type: ContactType
    notes: str | None
    created_at: datetime
    updated_at: datetime
