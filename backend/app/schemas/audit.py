"""Schemas da trilha de auditoria (nível Mare Nostrum)."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AuditLogItem(BaseModel):
    id: UUID
    user_id: UUID | None = None
    user_name: str | None = None
    user_role: str | None = None
    action: str
    entity_type: str
    entity_id: UUID | None = None
    summary: str | None = None
    created_at: datetime
    # Preenchido só na visão cross-tenant (Mare Nostrum) — qual campanha.
    tenant_name: str | None = None

    model_config = {"from_attributes": True}


class AuditLogList(BaseModel):
    items: list[AuditLogItem]
    total: int
