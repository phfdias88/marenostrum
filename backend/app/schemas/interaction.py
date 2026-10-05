"""Schemas Pydantic do modelo Interaction."""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InteractionCreate(BaseModel):
    """
    POST /contacts/{id}/interactions — registro MANUAL de interação
    (ex: mutirão WhatsApp marca "mensagem_enviada" por contato).
    O canal default é whatsapp; payload_data guarda contexto livre
    ({template, mutirao_id}...).
    """
    event_type: str = Field("mensagem_enviada", min_length=1, max_length=80)
    channel: str = Field("whatsapp", min_length=1, max_length=40)
    payload_data: dict[str, Any] = Field(default_factory=dict)


class InteractionRead(BaseModel):
    """Leitura via API (uso futuro: timeline de contato)."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    contact_id: UUID | None
    phone: str | None
    event_type: str | None
    channel: str
    external_event_id: str | None
    payload_data: dict[str, Any]
    received_at: datetime
    created_at: datetime
