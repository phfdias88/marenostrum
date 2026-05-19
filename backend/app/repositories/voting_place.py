"""Repository de VotingPlace. tenant_id em TODA query."""
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.models.voting_place import VotingPlace


class VotingPlaceRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    # ----------------------------------------------------------------- Read

    def count(
        self,
        *,
        tenant_id: UUID,
        election_year: int | None = None,
    ) -> int:
        stmt = select(func.count(VotingPlace.id)).where(
            VotingPlace.tenant_id == tenant_id,
        )
        if election_year is not None:
            stmt = stmt.where(VotingPlace.election_year == election_year)
        return int(self._db.execute(stmt).scalar_one())

    def list_paginated(
        self,
        *,
        tenant_id: UUID,
        limit: int,
        offset: int,
        election_year: int | None = None,
    ) -> list[VotingPlace]:
        stmt = select(VotingPlace).where(VotingPlace.tenant_id == tenant_id)
        if election_year is not None:
            stmt = stmt.where(VotingPlace.election_year == election_year)
        stmt = (
            stmt.order_by(VotingPlace.votes.desc(), VotingPlace.name.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._db.execute(stmt).scalars().all())

    def list_with_coords(
        self,
        *,
        tenant_id: UUID,
        election_year: int | None = None,
    ) -> list[VotingPlace]:
        """Usado pelo heatmap — apenas locais com lat/lng preenchidos."""
        stmt = select(VotingPlace).where(
            VotingPlace.tenant_id == tenant_id,
            VotingPlace.latitude.is_not(None),
            VotingPlace.longitude.is_not(None),
        )
        if election_year is not None:
            stmt = stmt.where(VotingPlace.election_year == election_year)
        return list(self._db.execute(stmt).scalars().all())

    def aggregate_stats(
        self,
        *,
        tenant_id: UUID,
        election_year: int | None = None,
    ) -> tuple[int, int, int]:
        """Retorna (total_places, total_votes, max_votes_em_um_local)."""
        stmt = select(
            func.count(VotingPlace.id),
            func.coalesce(func.sum(VotingPlace.votes), 0),
            func.coalesce(func.max(VotingPlace.votes), 0),
        ).where(VotingPlace.tenant_id == tenant_id)
        if election_year is not None:
            stmt = stmt.where(VotingPlace.election_year == election_year)
        row = self._db.execute(stmt).one()
        return int(row[0]), int(row[1]), int(row[2])

    # ----------------------------------------------------------------- Bulk

    def bulk_create(
        self,
        *,
        tenant_id: UUID,
        rows: list[dict[str, Any]],
    ) -> int:
        """INSERT VALUES (...), (...) — 1 round-trip pra centenas de linhas."""
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
        self._db.execute(insert(VotingPlace), payloads)
        return len(payloads)

    def delete_all_by_year(
        self,
        *,
        tenant_id: UUID,
        election_year: int | None,
    ) -> int:
        """Limpa antes de re-importar (idempotência por upload). Útil quando
        usuário sobe nova versão do CSV de um pleito."""
        stmt = delete(VotingPlace).where(VotingPlace.tenant_id == tenant_id)
        if election_year is None:
            stmt = stmt.where(VotingPlace.election_year.is_(None))
        else:
            stmt = stmt.where(VotingPlace.election_year == election_year)
        return self._db.execute(stmt).rowcount or 0
