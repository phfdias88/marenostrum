"""
Repository de contatos.

REGRA INVIOLAVEL: TODA query (insert/select/update/delete/count) filtra por
tenant_id. Metodos nunca aceitam payload "cru" — recebem dict ja validado
pelo Service e tenant_id explicito.
"""
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, func, insert, select, update
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

    def find_by_phone(
        self,
        *,
        tenant_id: UUID,
        phone: str,
    ) -> Contact | None:
        """Retorna contato com este telefone neste tenant, ou None."""
        stmt = select(Contact).where(
            Contact.tenant_id == tenant_id,
            Contact.phone == phone,
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

    # ----------------------------------------------------------- Bulk import

    def find_existing_phones(
        self,
        *,
        tenant_id: UUID,
        phones: list[str],
    ) -> set[str]:
        """Retorna o subconjunto de `phones` que ja existe no tenant."""
        if not phones:
            return set()
        stmt = select(Contact.phone).where(
            Contact.tenant_id == tenant_id,
            Contact.phone.in_(phones),
        )
        return {row[0] for row in self._db.execute(stmt).all() if row[0]}

    def bulk_create(
        self,
        *,
        tenant_id: UUID,
        rows: list[dict[str, Any]],
    ) -> int:
        """
        Insert em lote. UM INSERT VALUES (...), (...), (...) — milhares de
        registros em uma viagem ao banco.

        NOTA: o default `uuid4` definido no model so dispara via ORM `add()`.
        Em Core `insert()` precisamos pre-gerar IDs e timestamps. Tambem
        forcamos tenant_id (defesa contra payload corrompido).
        """
        if not rows:
            return 0

        now = datetime.now(timezone.utc)
        payloads = []
        for row in rows:
            row = {k: v for k, v in row.items() if k not in {"id", "tenant_id"}}
            payloads.append(
                {
                    "id": uuid4(),
                    "tenant_id": tenant_id,
                    "created_at": now,
                    "updated_at": now,
                    **row,
                }
            )

        self._db.execute(insert(Contact), payloads)
        return len(payloads)

    # -------------------------------------------------------------- Delete

    def delete(self, *, tenant_id: UUID, contact_id: UUID) -> bool:
        stmt = delete(Contact).where(
            Contact.id == contact_id,
            Contact.tenant_id == tenant_id,
        )
        result = self._db.execute(stmt)
        return (result.rowcount or 0) > 0
