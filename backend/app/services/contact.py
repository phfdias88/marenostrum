"""
Service de contatos: regras de negocio.

Controller -> Service -> Repository.
Service nao conhece HTTPException — levanta DomainError. Controller (camada
HTTP) traduz pra status via register_exception_handlers.

Geocoding: chamado em BackgroundTask do FastAPI quando o endereco mudou e
nao veio lat/lng explicito. Roda DEPOIS da resposta — UX nao espera Nominatim.
"""
from uuid import UUID

import structlog
from fastapi import BackgroundTasks

from app.core.errors import ConflictError, NotFoundError
from app.core.tenant_context import TenantContext
from app.models.contact import Contact
from app.repositories.contact import ContactRepository
from app.schemas.contact import ContactCreate, ContactUpdate
from app.utils.geocoding import geocode_and_persist_contact

log = structlog.get_logger("marenostrum.services.contact")


# -------------------------------------------------------- helpers privados


def _needs_geocoding(contact: Contact) -> bool:
    """
    Decide se vale rodar geocoding. Criterio:
    - Nao temos lat/lng ainda
    - Temos pelo menos algum sinal de endereco (address OU neighborhood)
    """
    has_coords = contact.latitude is not None and contact.longitude is not None
    has_addr_signal = bool(contact.address or contact.neighborhood)
    return (not has_coords) and has_addr_signal


def _schedule_geocoding(
    tasks: BackgroundTasks | None,
    contact: Contact,
) -> None:
    """Agenda geocoding em background. No-op se tasks=None (chamadas internas)."""
    if tasks is None or not _needs_geocoding(contact):
        return
    tasks.add_task(
        geocode_and_persist_contact,
        contact_id=contact.id,
        tenant_id=contact.tenant_id,
        address=contact.address,
        neighborhood=contact.neighborhood,
        city=contact.city,
        state=contact.state,
    )


# -------------------------------------------------------------------- class


class ContactService:
    def __init__(self, ctx: TenantContext) -> None:
        self._ctx = ctx
        self._repo = ContactRepository(ctx.db)

    # ---------------------------------------------------------------- Create

    def create_contact(
        self,
        payload: ContactCreate,
        background_tasks: BackgroundTasks | None = None,
    ) -> Contact:
        if payload.phone and self._repo.exists_by_phone(
            tenant_id=self._ctx.tenant_id,
            phone=payload.phone,
        ):
            raise ConflictError("Ja existe um contato com este telefone.")

        contact = self._repo.create(
            tenant_id=self._ctx.tenant_id,
            data=payload.model_dump(exclude_none=False),
        )
        self._ctx.db.commit()

        log.info(
            "contact_created",
            tenant_id=str(self._ctx.tenant_id),
            user_id=str(self._ctx.user_id),
            contact_id=str(contact.id),
        )

        _schedule_geocoding(background_tasks, contact)
        return contact

    # ------------------------------------------------------------------ Read

    def get_contact(self, contact_id: UUID) -> Contact:
        contact = self._repo.get_by_id(
            tenant_id=self._ctx.tenant_id,
            contact_id=contact_id,
        )
        if contact is None:
            raise NotFoundError("Contato nao encontrado.")
        return contact

    def list_contacts(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        search: str | None = None,
    ) -> tuple[list[Contact], int]:
        """Retorna (items, total) com filtro opcional por nome (ILIKE)."""
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
        # Normaliza: string vazia/whitespace = sem filtro
        search = search.strip() if search else None
        if search == "":
            search = None

        items = self._repo.list_paginated(
            tenant_id=self._ctx.tenant_id,
            limit=limit,
            offset=offset,
            search=search,
        )
        total = self._repo.count(
            tenant_id=self._ctx.tenant_id,
            search=search,
        )
        return items, total

    def list_for_map(self) -> list[Contact]:
        return self._repo.list_with_coords(tenant_id=self._ctx.tenant_id)

    # ---------------------------------------------------------------- Update

    def update_contact(
        self,
        contact_id: UUID,
        payload: ContactUpdate,
        background_tasks: BackgroundTasks | None = None,
    ) -> Contact:
        current = self.get_contact(contact_id)

        data = payload.model_dump(exclude_unset=True)
        new_phone = data.get("phone")
        if new_phone and new_phone != current.phone:
            if self._repo.exists_by_phone(
                tenant_id=self._ctx.tenant_id,
                phone=new_phone,
                exclude_id=contact_id,
            ):
                raise ConflictError("Ja existe outro contato com este telefone.")

        # Detecta mudanca de endereco — se mudou e lat/lng NAO foram fornecidos
        # explicitamente neste payload, vamos re-geocodificar
        address_fields = {"address", "neighborhood", "city", "state"}
        address_changed = any(
            f in data and data[f] != getattr(current, f) for f in address_fields
        )
        coords_provided = "latitude" in data or "longitude" in data

        updated = self._repo.update(
            tenant_id=self._ctx.tenant_id,
            contact_id=contact_id,
            data=data,
        )
        if updated is None:
            raise NotFoundError("Contato nao encontrado.")
        self._ctx.db.commit()

        log.info(
            "contact_updated",
            tenant_id=str(self._ctx.tenant_id),
            contact_id=str(contact_id),
            fields=list(data.keys()),
        )

        # Re-geocoda apenas se: endereco mudou E nao vieram coords no payload
        if address_changed and not coords_provided:
            _schedule_geocoding(background_tasks, updated)

        return updated

    # ---------------------------------------------------------------- Delete

    def delete_contact(self, contact_id: UUID) -> None:
        ok = self._repo.delete(
            tenant_id=self._ctx.tenant_id,
            contact_id=contact_id,
        )
        if not ok:
            raise NotFoundError("Contato nao encontrado.")
        self._ctx.db.commit()
        log.info(
            "contact_deleted",
            tenant_id=str(self._ctx.tenant_id),
            contact_id=str(contact_id),
        )
