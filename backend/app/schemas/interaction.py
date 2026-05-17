"""Schemas Pydantic do modelo Interaction."""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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
