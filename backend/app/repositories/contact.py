"""
Repository de contatos.

REGRA INVIOLAVEL: TODA query (insert/select/update/delete/count) filtra por
tenant_id. Metodos nunca aceitam payload "cru" — recebem dict ja validado
pelo Service e tenant_id explicito.

SOFT DELETE (Fase 10):
- delete() faz UPDATE is_active=False (preserva integridade referencial)
- Queries de LEITURA HUMANA filtram is_active=true por padrao:
  get_by_id, list_paginated, count, find_by_phone, list_with_coords, search
- Queries de VALIDACAO incluem inactive (alinhadas com a unique constraint
  do DB que e' global): exists_by_phone, find_existing_phones
  Razao: phone de contact soft-deleted ainda ocupa o slot unique.
"""
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session

from app.models.contact import Contact


class ContactRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    # -------------------------------------------------------------- Create

    def create(self, *, tenant_id: UUID, data: dict) -> Contact:
        data.pop("tenant_id", None)
        contact = Contact(tenant_id=tenant_id, **data)
        self._db.add(contact)
        self._db.flush()
        self._db.refresh(contact)
        return contact

    # ---------------------------------------------------------------- Read

    def get_by_id(
        self,
        *,
        tenant_id: UUID,
        contact_id: UUID,
        include_inactive: bool = False,
    ) -> Contact | None:
        stmt = select(Contact).where(
            Contact.id == contact_id,
            Contact.tenant_id == tenant_id,
        )
        if not include_inactive:
            stmt = stmt.where(Contact.is_active.is_(True))
        return self._db.execute(stmt).scalar_one_or_none()

    def find_by_phone(
        self,
        *,
        tenant_id: UUID,
        phone: str,
    ) -> Contact | None:
        """
        Busca contato ATIVO por telefone. Usado pelo webhook — soft-deleted
        nao deve linkar (webhook nao 'ressuscita' contato apagado).
        """
        stmt = select(Contact).where(
            Contact.tenant_id == tenant_id,
            Contact.phone == phone,
            Contact.is_active.is_(True),
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def exists_by_phone(
        self,
        *,
        tenant_id: UUID,
        phone: str,
        exclude_id: UUID | None = None,
    ) -> bool:
        """
        Verifica se phone existe (INCLUINDO inactive) — alinhado com a
        unique constraint do DB. Usado pra prevenir conflito antes do INSERT.
        """
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
        stmt = select(func.count(Contact.id)).where(
            Contact.tenant_id == tenant_id,
            Contact.is_active.is_(True),
        )
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
        Lista contatos ATIVOS do tenant.
        ILIKE no nome se search fornecido; case-insensitive.
        """
        stmt = select(Contact).where(
            Contact.tenant_id == tenant_id,
            Contact.is_active.is_(True),
        )
        if search:
            stmt = stmt.where(Contact.full_name.ilike(f"%{search}%"))
        stmt = (
            stmt.order_by(Contact.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._db.execute(stmt).scalars().all())

    def list_with_coords(self, *, tenant_id: UUID) -> list[Contact]:
        """Mapa — so contatos ATIVOS com lat/lng preenchidos."""
        stmt = select(Contact).where(
            Contact.tenant_id == tenant_id,
            Contact.is_active.is_(True),
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
        data.pop("tenant_id", None)
        data.pop("id", None)
        if not data:
            return self.get_by_id(tenant_id=tenant_id, contact_id=contact_id)

        # Update so' atinge contatos ATIVOS — soft-deleted fica "congelado".
        stmt = (
            update(Contact)
            .where(
                Contact.id == contact_id,
                Contact.tenant_id == tenant_id,
                Contact.is_active.is_(True),
            )
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
        """
        Retorna telefones que JA EXISTEM (incluindo inactive — alinhado
        com a unique constraint do DB).
        """
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

    def soft_delete(self, *, tenant_id: UUID, contact_id: UUID) -> bool:
        """
        SOFT DELETE: marca is_active=False. Preserva interactions/demands
        que referenciam este contato. Retorna False se ja estava inativo
        (idempotente do ponto de vista do cliente).
        """
        stmt = (
            update(Contact)
            .where(
                Contact.id == contact_id,
                Contact.tenant_id == tenant_id,
                Contact.is_active.is_(True),
            )
            .values(is_active=False)
        )
        result = self._db.execute(stmt)
        return (result.rowcount or 0) > 0

    # Hard delete removido. Se um dia precisarmos (LGPD: direito ao
    # esquecimento), criar metodo separado purge() que cascade
    # explicitamente em interactions/demands.
