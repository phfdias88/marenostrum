"""Backfill do status final de 2º turno (presidente/governador eleitos em
runoff ficaram com status "2º TURNO"). Re-baixa os ZIPs federais, escaneia
SÓ as linhas de NR_TURNO=2 e atualiza result_status por SQ_CANDIDATO.

Não re-importa votos — só corrige o status. Roda detached.
"""
from datetime import datetime, timezone

from sqlalchemy import text

from app.core.database import SessionLocal
from app.utils.tse_sync import (
    DATASETS, CACHE_DIR, _ensure_cache_dir, download_zip, iter_csv_rows, _i, _s,
)

FEDERAL = ["candidato_munzona_2018", "candidato_munzona_2022", "candidato_munzona_2014"]

def log(m): print(f"[{datetime.now(timezone.utc).isoformat()}] {m}", flush=True)

total_updated = 0
for ds in FEDERAL:
    meta = DATASETS[ds]
    _ensure_cache_dir()
    dest = CACHE_DIR / f"{ds}.zip"
    if not dest.exists():
        log(f"{ds}: baixando...")
        download_zip(meta["url"], dest, max_mb=meta.get("max_mb"))
    log(f"{ds}: escaneando 2º turno...")
    final = {}
    for _name, row in iter_csv_rows(dest, name_contains="_BRASIL"):
        if _i(row.get("NR_TURNO")) == 2:
            sq = _i(row.get("SQ_CANDIDATO"))
            st = _s(row.get("DS_SIT_TOT_TURNO"), 40) or None
            if sq and st:
                final[sq] = st
    log(f"{ds}: {len(final)} candidatos de 2º turno")
    with SessionLocal() as db:
        n = 0
        for sq, st in final.items():
            r = db.execute(
                text("UPDATE tse_candidates SET result_status=:st WHERE sq_candidato=:sq"),
                {"st": st, "sq": sq},
            )
            n += r.rowcount or 0
        db.commit()
        total_updated += n
        log(f"{ds}: {n} linhas atualizadas")
    # libera o zip pra economizar disco
    try:
        dest.unlink()
    except Exception:
        pass

log(f"=== BACKFILL COMPLETO: {total_updated} candidatos corrigidos ===")
