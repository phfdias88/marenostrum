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
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import cast, extract, func, insert, select, text, update
from sqlalchemy.dialects.postgresql import JSONB
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
        tag: str | None = None,
        created_by: UUID | None = None,
    ) -> int:
        stmt = select(func.count(Contact.id)).where(
            Contact.tenant_id == tenant_id,
            Contact.is_active.is_(True),
        )
        if search:
            stmt = stmt.where(Contact.full_name.ilike(f"%{search}%"))
        if tag:
            # tags @> '["x"]'::jsonb — bate indice GIN jsonb_path_ops
            stmt = stmt.where(Contact.tags.op("@>")(cast([tag], JSONB)))
        if created_by:
            stmt = stmt.where(Contact.created_by_user_id == created_by)
        return int(self._db.execute(stmt).scalar_one())

    def list_paginated(
        self,
        *,
        tenant_id: UUID,
        limit: int,
        offset: int,
        search: str | None = None,
        tag: str | None = None,
        created_by: UUID | None = None,
    ) -> list[Contact]:
        """
        Lista contatos ATIVOS do tenant.
        ILIKE no nome se search fornecido; case-insensitive.
        Filtro por tag usa contains (`tags @> '["x"]'`) — bate indice GIN.
        Filtro por created_by = quem cadastrou (id do usuário).
        """
        stmt = select(Contact).where(
            Contact.tenant_id == tenant_id,
            Contact.is_active.is_(True),
        )
        if search:
            stmt = stmt.where(Contact.full_name.ilike(f"%{search}%"))
        if tag:
            stmt = stmt.where(Contact.tags.op("@>")(cast([tag], JSONB)))
        if created_by:
            stmt = stmt.where(Contact.created_by_user_id == created_by)
        stmt = (
            stmt.order_by(Contact.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._db.execute(stmt).scalars().all())

    def list_creators(self, *, tenant_id: UUID) -> list[tuple[UUID, str]]:
        """Quem já cadastrou contato neste tenant (id + nome) — alimenta o filtro."""
        stmt = (
            select(
                Contact.created_by_user_id,
                func.max(Contact.created_by_name),
            )
            .where(
                Contact.tenant_id == tenant_id,
                Contact.is_active.is_(True),
                Contact.created_by_user_id.is_not(None),
            )
            .group_by(Contact.created_by_user_id)
        )
        rows = self._db.execute(stmt).all()
        return [(r[0], r[1] or "—") for r in rows]

    # ----------------------------------------------------- Tags & Birthdays

    def list_tag_summary(self, *, tenant_id: UUID) -> list[tuple[str, int]]:
        """
        Lista tags distintas no tenant + contagem de uso (sort: count DESC, tag ASC).
        Usa jsonb_array_elements_text — eficiente o suficiente pra ate' ~100k contatos.
        """
        sql = text(
            "SELECT tag, COUNT(*) AS n "
            "FROM contacts c, jsonb_array_elements_text(c.tags) AS tag "
            "WHERE c.tenant_id = :tid AND c.is_active = true "
            "GROUP BY tag "
            "ORDER BY n DESC, tag ASC "
            "LIMIT 200"
        )
        rows = self._db.execute(sql, {"tid": str(tenant_id)}).all()
        return [(r[0], int(r[1])) for r in rows]

    def list_birthdays(
        self,
        *,
        tenant_id: UUID,
        ref_date: date,
        days_ahead: int = 0,
    ) -> list[tuple[Contact, int]]:
        """
        Aniversariantes ATIVOS do tenant entre ref_date e ref_date+days_ahead (inclusive).
        Retorna lista de (contact, days_until). Lida com virada de ano.

        Estrategia: gera (mes,dia) das proximas N datas, faz IN — bate
        indice expression `ix_contacts_birthday_md`.
        """
        days_ahead = max(0, min(days_ahead, 60))  # defensiva: max 60 dias
        target_md: list[tuple[int, int]] = []
        for i in range(days_ahead + 1):
            d = ref_date + timedelta(days=i)
            target_md.append((d.month, d.day))

        # Monta tupla SQL ((m,d), (m,d), ...) via WHERE (month, day) IN ...
        # SQLAlchemy nao tem helper bonito pra tuple IN; usamos OR chain
        # — pra max 60 dias e' aceitavel
        stmt = select(Contact).where(
            Contact.tenant_id == tenant_id,
            Contact.is_active.is_(True),
            Contact.birth_date.is_not(None),
        )

        # Filtro composto (month,day) IN target_md via OR
        from sqlalchemy import and_, or_

        clauses = [
            and_(
                extract("month", Contact.birth_date) == m,
                extract("day", Contact.birth_date) == d,
            )
            for (m, d) in target_md
        ]
        if clauses:
            stmt = stmt.where(or_(*clauses))

        contacts = list(self._db.execute(stmt).scalars().all())

        # Calcula days_until por contato (em Python — barato pra max ~200 contatos)
        result: list[tuple[Contact, int]] = []
        for c in contacts:
            if c.birth_date is None:
                continue
            # Proxima ocorrencia do aniversario a partir de ref_date
            this_year = c.birth_date.replace(year=ref_date.year)
            if this_year < ref_date:
                # passou esse ano, vai pro proximo (so' acontece se days_ahead
                # cruzar virada de ano — fim de dezembro -> janeiro)
                try:
                    this_year = c.birth_date.replace(year=ref_date.year + 1)
                except ValueError:
                    # 29/fev em ano nao-bissexto: cai pra 28/fev
                    this_year = date(ref_date.year + 1, 2, 28)
            delta = (this_year - ref_date).days
            result.append((c, delta))

        # Ordena por days_until ASC, depois nome
        result.sort(key=lambda t: (t[1], t[0].full_name.lower()))
        return result

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
        created_by_user_id: UUID | None = None,
        created_by_name: str | None = None,
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
                    # Carimba quem importou — senão o contato fica com autor NULL
                    # e o próprio importador (staff) não consegue editá-lo pela
                    # regra "Comum edita só o que enviou".
                    "created_by_user_id": created_by_user_id,
                    "created_by_name": created_by_name,
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
