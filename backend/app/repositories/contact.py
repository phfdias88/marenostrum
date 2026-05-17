"""
Repository de contatos.

REGRA INVIOLAVEL: TODA query (insert/select/update/delete/count) filtra por
tenant_id. Metodos nunca aceitam payload "cru" — recebem dict ja validado
pelo Service e tenant_id explicito.
"""
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models.contact import Contact


class ContactRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    # -------------------------------------------------------------- Create

    def create(self, *, tenant_id: UUID, data: dict) -> Contact:
        # Defesa em profundidade: mesmo que `data` traga tenant_id por engano,
        # forcamos o valor recebido no parametro.
        data.pop("tenant_id", None)
        contact = Contact(tenant_id=tenant_id, **data)
        self._db.add(contact)
        self._db.flush()
        self._db.refresh(contact)
        return contact

    # ---------------------------------------------------------------- Read

    def get_by_id(self, *, tenant_id: UUID, contact_id: UUID) -> Contact | None:
        stmt = select(Contact).where(
            Contact.id == contact_id,
            Contact.tenant_id == tenant_id,
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def exists_by_phone(
        self,
        *,
        tenant_id: UUID,
        phone: str,
        exclude_id: UUID | None = None,
    ) -> bool:
        """exclude_id permite usar o mesmo phone do proprio registro em updates."""
        stmt = select(Contact.id).where(
            Contact.tenant_id == tenant_id,
            Contact.phone == phone,
        )
        if exclude_id is not None:
            stmt = stmt.where(Contact.id != exclude_id)
        return self._db.execute(stmt.limit(1)).first() is not None

    def count(
        self,
        *,
        tenant_id: UUID,
        search: str | None = None,
    ) -> int:
        stmt = select(func.count(Contact.id)).where(Contact.tenant_id == tenant_id)
        if search:
            stmt = stmt.where(Contact.full_name.ilike(f"%{search}%"))
        return int(self._db.execute(stmt).scalar_one())

    def list_paginated(
        self,
        *,
        tenant_id: UUID,
        limit: int,
        offset: int,
        search: str | None = None,
    ) -> list[Contact]:
        """
        Lista contatos do tenant. Se `search` for fornecido, aplica
        ILIKE no nome — case-insensitive, busca parcial.
        ILIKE usa indice quando a busca comeca com texto fixo; '%X%' faz seq scan.
        Para tabelas grandes, considere `pg_trgm` no futuro.
        """
        stmt = select(Contact).where(Contact.tenant_id == tenant_id)
        if search:
            stmt = stmt.where(Contact.full_name.ilike(f"%{search}%"))
        stmt = (
            stmt.order_by(Contact.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._db.execute(stmt).scalars().all())

    def list_with_coords(self, *, tenant_id: UUID) -> list[Contact]:
        """Usado pelo mapa: so contatos com lat/lng preenchidos."""
        stmt = select(Contact).where(
            Contact.tenant_id == tenant_id,
            Contact.latitude.is_not(None),
            Contact.longitude.is_not(None),
        )
        return list(self._db.execute(stmt).scalars().all())

    # -------------------------------------------------------------- Update

    def update(
        self,
        *,
        tenant_id: UUID,
        contact_id: UUID,
        data: dict,
    ) -> Contact | None:
        # Bloqueia mudanca de tenant_id por payload corrompido
        data.pop("tenant_id", None)
        data.pop("id", None)
        if not data:
            # Nada a atualizar — retorna o registro atual
            return self.get_by_id(tenant_id=tenant_id, contact_id=contact_id)

        stmt = (
            update(Contact)
            .where(Contact.id == contact_id, Contact.tenant_id == tenant_id)
            .values(**data)
            .returning(Contact)
        )
        row = self._db.execute(stmt).scalar_one_or_none()
        if row is not None:
            self._db.refresh(row)
        return row

    # -------------------------------------------------------------- Delete

    def delete(self, *, tenant_id: UUID, contact_id: UUID) -> bool:
        stmt = delete(Contact).where(
            Contact.id == contact_id,
            Contact.tenant_id == tenant_id,
        )
        result = self._db.execute(stmt)
        return (result.rowcount or 0) > 0
