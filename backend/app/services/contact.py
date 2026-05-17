"""
Service de contatos: regras de negocio.

Camadas:
  Controller -> Service -> Repository
A Controller NUNCA fala direto com o Repository, e o Service NUNCA conhece
HTTPException - ele levanta DomainError, e a camada HTTP traduz.
"""
import structlog

from app.core.errors import ConflictError
from app.core.tenant_context import TenantContext
from app.models.contact import Contact
from app.repositories.contact import ContactRepository
from app.schemas.contact import ContactCreate

log = structlog.get_logger("marenostrum.services.contact")


class ContactService:
    def __init__(self, ctx: TenantContext) -> None:
        self._ctx = ctx
        self._repo = ContactRepository(ctx.db)

    def create_contact(self, payload: ContactCreate) -> Contact:
        # Regra de negocio: telefone unico por tenant (quando informado).
        if payload.phone and self._repo.exists_by_phone(
            tenant_id=self._ctx.tenant_id,
            phone=payload.phone,
        ):
            raise ConflictError("Ja existe um contato com este telefone.")

        contact = self._repo.create(
            tenant_id=self._ctx.tenant_id,
            data=payload.model_dump(exclude_none=False),
        )
        # Commit aqui: Service e quem decide o limite transacional.
        self._ctx.db.commit()

        log.info(
            "contact_created",
            tenant_id=str(self._ctx.tenant_id),
            user_id=str(self._ctx.user_id),
            contact_id=str(contact.id),
        )
        return contact

    def list_contacts(self, *, limit: int = 50, offset: int = 0) -> list[Contact]:
        # Limites defensivos contra cliente abusivo
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
        return self._repo.list_paginated(
            tenant_id=self._ctx.tenant_id,
            limit=limit,
            offset=offset,
        )
