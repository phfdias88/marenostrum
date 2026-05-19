"""Service de VotingPlace — import CSV, listagem, heatmap."""
import structlog

from app.core.tenant_context import TenantContext
from app.models.voting_place import VotingPlace
from app.repositories.voting_place import VotingPlaceRepository
from app.schemas.voting_place import (
    HeatmapPoint,
    HeatmapResponse,
    VotingImportResult,
)
from app.utils.voting_import import parse_voting_csv

log = structlog.get_logger("marenostrum.services.voting_place")


class VotingPlaceService:
    def __init__(self, ctx: TenantContext) -> None:
        self._ctx = ctx
        self._repo = VotingPlaceRepository(ctx.db)

    # ----------------------------------------------------------------- Read

    def list_places(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        election_year: int | None = None,
    ) -> tuple[list[VotingPlace], int]:
        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        items = self._repo.list_paginated(
            tenant_id=self._ctx.tenant_id,
            limit=limit, offset=offset,
            election_year=election_year,
        )
        total = self._repo.count(
            tenant_id=self._ctx.tenant_id,
            election_year=election_year,
        )
        return items, total

    def heatmap(
        self,
        *,
        election_year: int | None = None,
    ) -> HeatmapResponse:
        """
        Pega todos locais com lat/lng e normaliza intensidade [0,1] dividindo
        pelo `max(votes)`. Leaflet.heat espera valores nesse range.
        """
        places = self._repo.list_with_coords(
            tenant_id=self._ctx.tenant_id,
            election_year=election_year,
        )
        total_places, total_votes, max_votes = self._repo.aggregate_stats(
            tenant_id=self._ctx.tenant_id,
            election_year=election_year,
        )

        # Normaliza intensidade [0, 1]. Se max_votes=0, intensidade=0 (sem heat).
        denom = max(max_votes, 1)
        points = [
            HeatmapPoint(
                lat=p.latitude,  # type: ignore[arg-type]
                lng=p.longitude,  # type: ignore[arg-type]
                intensity=p.votes / denom,
                votes=p.votes,
                name=p.name,
            )
            for p in places
        ]

        return HeatmapResponse(
            points=points,
            total_places=total_places,
            total_votes=total_votes,
            max_votes=max_votes,
        )

    # --------------------------------------------------------------- Import

    def import_csv(
        self,
        file_bytes: bytes,
        *,
        election_year: int | None = None,
        replace_existing: bool = False,
    ) -> VotingImportResult:
        """
        Importa locais em lote. Se `replace_existing=True`, apaga TODOS os
        locais do tenant (do ano informado) antes de inserir — idempotência
        por upload, usuário pode subir nova versão do CSV.
        """
        rows, errors = parse_voting_csv(
            file_bytes, default_election_year=election_year,
        )
        total_rows = len(rows) + len(errors)

        if replace_existing:
            removed = self._repo.delete_all_by_year(
                tenant_id=self._ctx.tenant_id,
                election_year=election_year,
            )
            log.info(
                "voting_places_replaced",
                tenant_id=str(self._ctx.tenant_id),
                removed=removed,
            )

        inserted = self._repo.bulk_create(
            tenant_id=self._ctx.tenant_id,
            rows=rows,
        )
        self._ctx.db.commit()

        log.info(
            "voting_places_imported",
            tenant_id=str(self._ctx.tenant_id),
            user_id=str(self._ctx.user_id),
            imported=inserted,
            skipped=len(errors),
            election_year=election_year,
        )

        return VotingImportResult(
            imported=inserted,
            skipped=len(errors),
            total_rows=total_rows,
            errors=errors[:50],
        )
