"""Backfill do status final de 2º turno (presidente/governador eleitos em
runoff ficaram com status "2º TURNO"). Re-baixa os ZIPs federais, escaneia
SÓ as linhas de NR_TURNO=2 e atualiza result_status por SQ_CANDIDATO.

Não re-importa votos — só corrige o status. Roda detached.
"""
import os
from datetime import datetime, timezone

from sqlalchemy import text

from app.core.database import SessionLocal
from app.utils.tse_sync import (
    DATASETS, CACHE_DIR, _ensure_cache_dir, download_zip, iter_csv_rows, _i, _s,
)

# TODOS os anos que podem ter ELEITO em 2º turno. Antes só listava os federais
# (pres/gov), então PREFEITOS de capital eleitos em 2º turno (Paes 2020,
# Crivella 2016) ficaram presos em "2º TURNO". Os `votacao_candidato_munzona_*`
# — municipais e federais — têm arquivo `_BRASIL` consolidado (o filtro do
# iter_csv_rows funciona) e o scan lê NR_TURNO=2 = o resultado FINAL.
RUNOFF_DATASETS = [
    "candidato_munzona_2024", "candidato_munzona_2022", "candidato_munzona_2020",
    "candidato_munzona_2018", "candidato_munzona_2016", "candidato_munzona_2014",
]
# Filtro opcional por ano (evita re-baixar zips já corretos). Ex.:
#   RUNOFF_YEARS=2016,2020,2024 python backfill_runoff.py
_only = os.environ.get("RUNOFF_YEARS", "").strip()
if _only:
    _yrs = {y.strip() for y in _only.split(",") if y.strip()}
    RUNOFF_DATASETS = [d for d in RUNOFF_DATASETS if d.rsplit("_", 1)[-1] in _yrs]

def log(m): print(f"[{datetime.now(timezone.utc).isoformat()}] {m}", flush=True)

log(f"datasets a processar: {RUNOFF_DATASETS}")
total_updated = 0
for ds in RUNOFF_DATASETS:
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
