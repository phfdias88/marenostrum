"""Repository de interactions (webhooks salvos)."""
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.interaction import Interaction


class InteractionRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self,
        *,
        tenant_id: UUID,
        contact_id: UUID | None,
        phone: str | None,
        event_type: str | None,
        channel: str,
        external_event_id: str | None,
        payload_data: dict[str, Any],
    ) -> Interaction:
        interaction = Interaction(
            tenant_id=tenant_id,
            contact_id=contact_id,
            phone=phone,
            event_type=event_type,
            channel=channel,
            external_event_id=external_event_id,
            payload_data=payload_data,
        )
        self._db.add(interaction)
        self._db.flush()
        self._db.refresh(interaction)
        return interaction

    def find_by_external_id(
        self,
        *,
        tenant_id: UUID,
        external_event_id: str,
    ) -> Interaction | None:
        """Usado pra idempotencia (futuramente)."""
        stmt = select(Interaction).where(
            Interaction.tenant_id == tenant_id,
            Interaction.external_event_id == external_event_id,
        )
        return self._db.execute(stmt).scalar_one_or_none()
