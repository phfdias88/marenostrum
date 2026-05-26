"""
One-shot: importa receita/despesa de campanha (prestacao de contas) e
atualiza candidates.revenue_total / expense_total por sq_candidato.

Uso:
    docker compose exec api python -m app.utils.tse_finance

Zip ~1.2GB (transacoes linha-a-linha). Agregamos por sq em memoria
(dict ~450k entradas, ok). Receitas: receitas_*_BRASIL.csv (VR_RECEITA).
Despesas: despesas_contratadas_*_BRASIL.csv (VR_DESPESA_CONTRATADA).
"""
from __future__ import annotations

import logging
import zipfile
from pathlib import Path

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.utils.tse_sync import (
    CACHE_DIR,
    TSE_BASE_URL,
    _ensure_cache_dir,
    _i,
    download_zip,
    iter_csv_rows,
)

log = structlog.get_logger("marenostrum.finance")

URL = f"{TSE_BASE_URL}/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_2024.zip"
CHUNK = 2000


def _parse_brl(v: str | None) -> float:
    if not v:
        return 0.0
    try:
        return float(v.strip().replace(".", "").replace(",", "."))
    except (ValueError, AttributeError):
        return 0.0


def _csvs_for(zip_path: Path, prefix: str) -> list[str]:
    """CSVs que comecam com prefix; prioriza o _BRASIL se existir."""
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    match = [n for n in names if prefix in n.lower()]
    brasil = [n for n in match if "brasil" in n.lower()]
    return brasil or match


def _sum_by_sq(zip_path: Path, csv_names: list[str], value_col: str) -> dict[int, float]:
    acc: dict[int, float] = {}
    name_set = set(csv_names)
    for fname, row in iter_csv_rows(zip_path):
        if fname not in name_set:
            continue
        sq = _i(row.get("SQ_CANDIDATO"))
        if not sq:
            continue
        acc[sq] = acc.get(sq, 0.0) + _parse_brl(row.get(value_col))
    return {sq: round(v, 2) for sq, v in acc.items()}


def populate(db: Session) -> dict[str, int]:
    _ensure_cache_dir()
    zp = CACHE_DIR / "prestacao_contas_2024.zip"
    if not zp.exists():
        download_zip(URL, zp)

    rec_csvs = _csvs_for(zp, "receitas_candidatos")
    desp_csvs = _csvs_for(zp, "despesas_contratadas_candidatos")
    log.info("finance_csvs", receitas=rec_csvs[:2], despesas=desp_csvs[:2])

    revenue = _sum_by_sq(zp, rec_csvs, "VR_RECEITA")
    log.info("finance_revenue_collected", n=len(revenue))
    expense = _sum_by_sq(zp, desp_csvs, "VR_DESPESA_CONTRATADA")
    log.info("finance_expense_collected", n=len(expense))

    rev_stmt = text(
        "UPDATE tse_candidates SET revenue_total = :v, updated_at = now() WHERE sq_candidato = :sq"
    )
    exp_stmt = text(
        "UPDATE tse_candidates SET expense_total = :v, updated_at = now() WHERE sq_candidato = :sq"
    )
    rrows = [{"sq": sq, "v": v} for sq, v in revenue.items()]
    erows = [{"sq": sq, "v": v} for sq, v in expense.items()]
    for i in range(0, len(rrows), CHUNK):
        db.execute(rev_stmt, rrows[i : i + CHUNK]); db.commit()
    for i in range(0, len(erows), CHUNK):
        db.execute(exp_stmt, erows[i : i + CHUNK]); db.commit()
    log.info("finance_done", revenue=len(rrows), expense=len(erows))
    return {"revenue": len(rrows), "expense": len(erows)}


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as db:
        print("Resultado:", populate(db))


if __name__ == "__main__":
    main()
