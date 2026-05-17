"""
Repository de contatos.

REGRA INVIOLAVEL DESTA CAMADA: TODO metodo recebe `tenant_id` e o aplica em
TODA query (insert, select, update, delete). Nunca aceitar request "crua" -
sempre dados ja validados pelo Service.
"""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.contact import Contact


class ContactRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self,
        *,
        tenant_id: UUID,
        data: dict,
    ) -> Contact:
        """Cria contato JA com tenant_id injetado. Nao usa data.get('tenant_id')."""
        contact = Contact(tenant_id=tenant_id, **data)
        self._db.add(contact)
        self._db.flush()   # garante id sem fazer commit (Service decide o commit)
        self._db.refresh(contact)
        return contact

    def get_by_id(self, *, tenant_id: UUID, contact_id: UUID) -> Contact | None:
        # Filtro duplo: id E tenant_id. Mesmo que um id seja "advinhado", a
        # query nao retorna nada se o contato pertencer a outro tenant.
        stmt = select(Contact).where(
            Contact.id == contact_id,
            Contact.tenant_id == tenant_id,
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def exists_by_phone(self, *, tenant_id: UUID, phone: str) -> bool:
        stmt = select(Contact.id).where(
            Contact.tenant_id == tenant_id,
            Contact.phone == phone,
        ).limit(1)
        return self._db.execute(stmt).first() is not None

    def list_paginated(
        self,
        *,
        tenant_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Contact]:
        stmt = (
            select(Contact)
            .where(Contact.tenant_id == tenant_id)
            .order_by(Contact.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._db.execute(stmt).scalars().all())
