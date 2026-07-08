"""
Runner do pipeline de enriquecimento de Locais de Votação (task pós-ingestão).

Pega os locais SEM coordenada real (geo_source 'unmapped' ou 'centroid') e tenta
recuperar a coordenada via ViaCEP -> Nominatim (services.location_enrichment).
Sucesso -> grava lat/lng + geo_source='nominatim'. Falha -> deixa como está
(continua na lista de Não Mapeados / no centroide impreciso).

É SÍNCRONO no DB e ASSÍNCRONO no geocode (que já faz throttle de 1s do Nominatim),
então processa ~1 local/segundo. Use SEMPRE escopado (por município ou UF) e com
LIMIT — rodar o Brasil inteiro levaria horas.

Uso (dentro do container api):
    docker compose exec -T \
      -e ENRICH_MUNI=<municipality_id> -e ENRICH_LIMIT=300 \
      api python -m app.utils.enrich_voting_places
Env:
    ENRICH_MUNI   municipality_id (UUID) — escopo por município (recomendado)
    ENRICH_UF     UF (ex: RJ) — escopo por estado (se não passar MUNI)
    ENRICH_YEAR   ano (default 2024)
    ENRICH_LIMIT  máximo de locais a processar nesta rodada (default 300)
    ENRICH_SOURCES  origens a reprocessar (default "unmapped,centroid")
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from sqlalchemy import text

from app.core.database import SessionLocal
from app.services.location_enrichment import enrich_location
from app.utils.tse_sync import _coord_in_brazil


def _log(m: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat()}] {m}", flush=True)


async def run() -> None:
    muni = os.environ.get("ENRICH_MUNI", "").strip()
    uf = os.environ.get("ENRICH_UF", "").strip().upper()
    year = int(os.environ.get("ENRICH_YEAR", "2024"))
    limit = int(os.environ.get("ENRICH_LIMIT", "300"))
    sources = [
        s.strip() for s in os.environ.get("ENRICH_SOURCES", "unmapped,centroid").split(",")
        if s.strip()
    ]
    if not muni and not uf:
        _log("ERRO: informe ENRICH_MUNI (município) ou ENRICH_UF (estado).")
        return

    where = ["v.year = :year", "v.geo_source = ANY(:sources)"]
    params: dict = {"year": year, "sources": sources, "limit": limit}
    if muni:
        where.append("v.municipality_id = :muni")
        params["muni"] = muni
    elif uf:
        where.append("m.state = :uf")
        params["uf"] = uf
    sql = (
        "SELECT v.id, v.name, v.address, v.neighborhood, m.name AS muni, m.state AS uf "
        "FROM tse_voting_places v JOIN tse_municipalities m ON m.id = v.municipality_id "
        "WHERE " + " AND ".join(where) + " ORDER BY v.electors_total DESC LIMIT :limit"
    )

    with SessionLocal() as db:
        targets = db.execute(text(sql), params).mappings().all()
        _log(f"{len(targets)} locais a enriquecer (year={year}, sources={sources}, "
             f"escopo={'muni=' + muni if muni else 'uf=' + uf})")

        found = 0
        for i, t in enumerate(targets, 1):
            coord = await enrich_location(
                name=t["name"],
                address=t["address"],
                neighborhood=t["neighborhood"],
                municipality=t["muni"],
                uf=t["uf"],
            )
            if coord and _coord_in_brazil(coord[0], coord[1]):
                db.execute(
                    text(
                        "UPDATE tse_voting_places SET latitude=:lat, longitude=:lng, "
                        "geo_source='nominatim', updated_at=now() WHERE id=:id"
                    ),
                    {"lat": coord[0], "lng": coord[1], "id": t["id"]},
                )
                db.commit()
                found += 1
            if i % 25 == 0:
                _log(f"  {i}/{len(targets)} processados, {found} recuperados")

        _log(f"=== ENRIQUECIMENTO COMPLETO: {found}/{len(targets)} recuperados ===")


if __name__ == "__main__":
    asyncio.run(run())
