"""Repository de interactions (webhooks salvos)."""
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
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

    def list_by_contact(
        self,
        *,
        tenant_id: UUID,
        contact_id: UUID,
        limit: int,
        offset: int,
    ) -> list[Interaction]:
        """
        Lista interacoes vinculadas a um contato, mais recentes primeiro.
        Filtro DUPLO (tenant_id + contact_id) garante isolamento —
        mesmo que contact_id seja "advinhado", outro tenant nao vaza.
        """
        stmt = (
            select(Interaction)
            .where(
                Interaction.tenant_id == tenant_id,
                Interaction.contact_id == contact_id,
            )
            .order_by(Interaction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._db.execute(stmt).scalars().all())

    def count_by_contact(
        self,
        *,
        tenant_id: UUID,
        contact_id: UUID,
    ) -> int:
        stmt = select(func.count(Interaction.id)).where(
            Interaction.tenant_id == tenant_id,
            Interaction.contact_id == contact_id,
        )
        return int(self._db.execute(stmt).scalar_one())

    # ------------------------------------------------- orfas (leads WhatsApp)

    def list_orphan_groups(
        self,
        *,
        tenant_id: UUID,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Interacoes ORFAS (contact_id NULL, phone preenchido) agrupadas por
        telefone, mais recentes primeiro. Retorna dicts:
            {phone, count, last_event_type, last_at}

        2 queries: agregacao + event_type da interacao mais recente por
        telefone (varredura em Python — max `limit` grupos, volume pequeno).
        """
        last_at = func.max(Interaction.received_at).label("last_at")
        stmt = (
            select(
                Interaction.phone,
                func.count(Interaction.id).label("cnt"),
                last_at,
            )
            .where(
                Interaction.tenant_id == tenant_id,
                Interaction.contact_id.is_(None),
                Interaction.phone.is_not(None),
            )
            .group_by(Interaction.phone)
            .order_by(last_at.desc())
            .limit(limit)
        )
        groups = self._db.execute(stmt).all()
        if not groups:
            return []

        phones = [g[0] for g in groups]
        ev_stmt = (
            select(Interaction.phone, Interaction.event_type)
            .where(
                Interaction.tenant_id == tenant_id,
                Interaction.contact_id.is_(None),
                Interaction.phone.in_(phones),
            )
            .order_by(Interaction.received_at.desc())
        )
        last_event: dict[str, str | None] = {}
        for phone, event_type in self._db.execute(ev_stmt).all():
            if phone not in last_event:
                last_event[phone] = event_type

        return [
            {
                "phone": g[0],
                "count": int(g[1]),
                "last_event_type": last_event.get(g[0]),
                "last_at": g[2],
            }
            for g in groups
        ]

    def list_orphan_phones(self, *, tenant_id: UUID) -> list[str]:
        """Telefones DISTINTOS das interacoes orfas do tenant (pro relink)."""
        stmt = (
            select(Interaction.phone)
            .where(
                Interaction.tenant_id == tenant_id,
                Interaction.contact_id.is_(None),
                Interaction.phone.is_not(None),
            )
            .distinct()
        )
        return [r[0] for r in self._db.execute(stmt).all()]

    def relink_phones(
        self,
        *,
        tenant_id: UUID,
        phones: list[str],
        contact_id: UUID,
    ) -> int:
        """Vincula TODAS as orfas do tenant com phone na lista ao contato.
        Retorna quantas linhas foram atualizadas."""
        if not phones:
            return 0
        stmt = (
            update(Interaction)
            .where(
                Interaction.tenant_id == tenant_id,
                Interaction.contact_id.is_(None),
                Interaction.phone.in_(phones),
            )
            .values(contact_id=contact_id)
        )
        return int(self._db.execute(stmt).rowcount or 0)
