"""
Service de contatos: regras de negocio.

Controller -> Service -> Repository.
Service nunca conhece HTTPException — levanta DomainError. Controller (camada
HTTP) e quem traduz pra status code via register_exception_handlers.
"""
from uuid import UUID

import structlog

from app.core.errors import ConflictError, NotFoundError
from app.core.tenant_context import TenantContext
from app.models.contact import Contact
from app.repositories.contact import ContactRepository
from app.schemas.contact import ContactCreate, ContactUpdate

log = structlog.get_logger("marenostrum.services.contact")


class ContactService:
    def __init__(self, ctx: TenantContext) -> None:
        self._ctx = ctx
        self._repo = ContactRepository(ctx.db)

    # ---------------------------------------------------------------- Create

    def create_contact(self, payload: ContactCreate) -> Contact:
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
    ) -> tuple[list[Contact], int]:
        """Retorna (items, total) — total alimenta a paginacao da DataTable."""
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
        items = self._repo.list_paginated(
            tenant_id=self._ctx.tenant_id,
            limit=limit,
            offset=offset,
        )
        total = self._repo.count(tenant_id=self._ctx.tenant_id)
        return items, total

    def list_for_map(self) -> list[Contact]:
        return self._repo.list_with_coords(tenant_id=self._ctx.tenant_id)

    # ---------------------------------------------------------------- Update

    def update_contact(self, contact_id: UUID, payload: ContactUpdate) -> Contact:
        # Garante que existe (e pertence ao tenant) antes de validar regras
        current = self.get_contact(contact_id)

        # Se o telefone mudou, valida unicidade ignorando o proprio registro
        data = payload.model_dump(exclude_unset=True)
        new_phone = data.get("phone")
        if new_phone and new_phone != current.phone:
            if self._repo.exists_by_phone(
                tenant_id=self._ctx.tenant_id,
                phone=new_phone,
                exclude_id=contact_id,
            ):
                raise ConflictError("Ja existe outro contato com este telefone.")

        updated = self._repo.update(
            tenant_id=self._ctx.tenant_id,
            contact_id=contact_id,
            data=data,
        )
        if updated is None:
            # Race condition rara (deletado entre get e update)
            raise NotFoundError("Contato nao encontrado.")

        self._ctx.db.commit()
        log.info(
            "contact_updated",
            tenant_id=str(self._ctx.tenant_id),
            contact_id=str(contact_id),
            fields=list(data.keys()),
        )
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
