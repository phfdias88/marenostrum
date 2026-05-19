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

    def aggregate_by_neighborhood(
        self,
        *,
        tenant_id: UUID,
        election_year: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Agrupa votos por bairro. Linhas com bairro NULO ou vazio sao agrupadas
        sob '(Sem bairro)' pra nao perder dados na visualizacao.

        Retorna lista ordenada por total_votes desc:
          [{neighborhood, total_votes, total_places, total_voters,
            avg_lat, avg_lng}, ...]
        """
        # Coalesce trata NULL como "(Sem bairro)" no agrupamento
        nb = func.coalesce(
            func.nullif(func.trim(VotingPlace.neighborhood), ""),
            "(Sem bairro)",
        ).label("neighborhood")

        stmt = (
            select(
                nb,
                func.count(VotingPlace.id).label("total_places"),
                func.coalesce(func.sum(VotingPlace.votes), 0).label("total_votes"),
                func.coalesce(func.sum(VotingPlace.total_voters), 0).label(
                    "total_voters",
                ),
                func.avg(VotingPlace.latitude).label("avg_lat"),
                func.avg(VotingPlace.longitude).label("avg_lng"),
            )
            .where(VotingPlace.tenant_id == tenant_id)
            .group_by(nb)
            .order_by(func.coalesce(func.sum(VotingPlace.votes), 0).desc())
        )
        if election_year is not None:
            stmt = stmt.where(VotingPlace.election_year == election_year)

        rows = self._db.execute(stmt).all()
        return [
            {
                "neighborhood": r.neighborhood,
                "total_places": int(r.total_places),
                "total_votes": int(r.total_votes),
                "total_voters": int(r.total_voters) if r.total_voters else None,
                "avg_lat": float(r.avg_lat) if r.avg_lat is not None else None,
                "avg_lng": float(r.avg_lng) if r.avg_lng is not None else None,
            }
            for r in rows
        ]

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
