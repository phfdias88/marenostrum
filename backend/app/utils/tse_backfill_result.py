"""
One-shot: backfill do campo result_status (DS_SIT_TOT_TURNO) nos candidatos
ja importados, sem precisar re-importar o dataset inteiro.

Uso:
    docker compose exec api python -m app.utils.tse_backfill_result

Le o zip votacao_candidato_munzona_2024 (baixa se nao tiver cache),
extrai {SQ_CANDIDATO: DS_SIT_TOT_TURNO}, bulk-update por sq_candidato.
"""
from __future__ import annotations

import logging
from pathlib import Path

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.utils.tse_sync import (
    CACHE_DIR,
    DATASETS,
    _ensure_cache_dir,
    _i,
    _s,
    download_zip,
    iter_csv_rows,
)

log = structlog.get_logger("marenostrum.backfill_result")

CHUNK = 2000


def populate(db: Session) -> dict[str, int]:
    meta = DATASETS["candidato_munzona_2024"]
    _ensure_cache_dir()
    zip_path = CACHE_DIR / "candidato_munzona_2024.zip"
    if not zip_path.exists():
        log.info("backfill_download", url=meta["url"])
        download_zip(meta["url"], zip_path)

    # Extrai {sq: result_status} — dataset tem 1 linha por (cand, municipio),
    # mas DS_SIT_TOT_TURNO e o mesmo pro candidato. Pega a primeira ocorrencia.
    result_by_sq: dict[int, str] = {}
    rows_read = 0
    for _, row in iter_csv_rows(zip_path):
        rows_read += 1
        sq = _i(row.get("SQ_CANDIDATO"))
        if not sq or sq in result_by_sq:
            continue
        rs = _s(row.get("DS_SIT_TOT_TURNO"), 40)
        if rs:
            result_by_sq[sq] = rs
        if rows_read % 200_000 == 0:
            log.info("backfill_read", rows=rows_read, unique=len(result_by_sq))

    log.info("backfill_parsed", rows=rows_read, unique_sq=len(result_by_sq))

    # Bulk update via Core SQL executemany
    stmt = text(
        "UPDATE tse_candidates SET result_status = :rs, updated_at = now() "
        "WHERE sq_candidato = :sq AND (result_status IS DISTINCT FROM :rs)"
    )
    updates = [{"sq": sq, "rs": rs} for sq, rs in result_by_sq.items()]
    updated = 0
    for i in range(0, len(updates), CHUNK):
        chunk = updates[i : i + CHUNK]
        res = db.execute(stmt, chunk)
        db.commit()
        updated += len(chunk)
        if (i // CHUNK) % 10 == 0:
            log.info("backfill_chunk", processed=updated, total=len(updates))

    return {"rows_read": rows_read, "unique_sq": len(result_by_sq), "updated": updated}


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as db:
        result = populate(db)
    print("Resultado:", result)


if __name__ == "__main__":
    main()
