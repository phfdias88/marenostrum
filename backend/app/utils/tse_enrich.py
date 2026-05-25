"""
One-shot: enriquece candidatos com patrimonio (bem_candidato) e redes sociais
(rede_social_candidato), de 2024 e 2022.

Uso:
    docker compose exec api python -m app.utils.tse_enrich

Atualiza tse_candidates.assets_total e .social_links por sq_candidato.
Dedupe defensivo (NR_ORDEM / URL) caso o zip tenha BRASIL + por-UF.
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
    TSE_BASE_URL,
    _ensure_cache_dir,
    _i,
    download_zip,
    iter_csv_rows,
)

log = structlog.get_logger("marenostrum.enrich")

DATASETS = {
    "rede_social_2024": f"{TSE_BASE_URL}/consulta_cand/rede_social_candidato_2024.zip",
    "rede_social_2022": f"{TSE_BASE_URL}/consulta_cand/rede_social_candidato_2022.zip",
    "bem_2024": f"{TSE_BASE_URL}/bem_candidato/bem_candidato_2024.zip",
    "bem_2022": f"{TSE_BASE_URL}/bem_candidato/bem_candidato_2022.zip",
}
CHUNK = 2000


def _parse_brl(v: str | None) -> float:
    """'1.234.567,89' -> 1234567.89"""
    if not v:
        return 0.0
    try:
        return float(v.strip().replace(".", "").replace(",", "."))
    except (ValueError, AttributeError):
        return 0.0


def _download(key: str) -> Path:
    _ensure_cache_dir()
    dest = CACHE_DIR / f"{key}.zip"
    if not dest.exists():
        download_zip(DATASETS[key], dest)
    return dest


def collect_social(db: Session) -> dict[int, list[str]]:
    by_sq: dict[int, list[str]] = {}
    for key in ("rede_social_2024", "rede_social_2022"):
        zp = _download(key)
        for _, row in iter_csv_rows(zp):
            sq = _i(row.get("SQ_CANDIDATO"))
            url = (row.get("DS_URL") or "").strip()
            if not sq or not url or url in ("#NULO#", "-1", "#NE#"):
                continue
            lst = by_sq.setdefault(sq, [])
            if url not in lst and len(lst) < 8:
                lst.append(url)
    log.info("enrich_social_collected", candidates=len(by_sq))
    return by_sq


def collect_assets(db: Session) -> dict[int, float]:
    # dedupe por (sq, nr_ordem) pra nao somar 2x se houver BRASIL+UF
    seen: dict[int, dict[int, float]] = {}
    for key in ("bem_2024", "bem_2022"):
        zp = _download(key)
        for _, row in iter_csv_rows(zp):
            sq = _i(row.get("SQ_CANDIDATO"))
            if not sq:
                continue
            ordem = _i(row.get("NR_ORDEM_BEM_CANDIDATO"))
            val = _parse_brl(row.get("VR_BEM_CANDIDATO"))
            seen.setdefault(sq, {})[ordem] = val
    totals = {sq: round(sum(items.values()), 2) for sq, items in seen.items()}
    log.info("enrich_assets_collected", candidates=len(totals))
    return totals


def populate(db: Session) -> dict[str, int]:
    social = collect_social(db)
    assets = collect_assets(db)

    # Atualiza social_links
    import json as _json

    social_stmt = text(
        "UPDATE tse_candidates SET social_links = CAST(:links AS JSON), "
        "updated_at = now() WHERE sq_candidato = :sq"
    )
    rows = [{"sq": sq, "links": _json.dumps(links)} for sq, links in social.items()]
    for i in range(0, len(rows), CHUNK):
        db.execute(social_stmt, rows[i : i + CHUNK])
        db.commit()
    log.info("enrich_social_updated", n=len(rows))

    # Atualiza assets_total
    asset_stmt = text(
        "UPDATE tse_candidates SET assets_total = :total, updated_at = now() "
        "WHERE sq_candidato = :sq"
    )
    arows = [{"sq": sq, "total": t} for sq, t in assets.items()]
    for i in range(0, len(arows), CHUNK):
        db.execute(asset_stmt, arows[i : i + CHUNK])
        db.commit()
    log.info("enrich_assets_updated", n=len(arows))

    return {"social": len(rows), "assets": len(arows)}


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as db:
        print("Resultado:", populate(db))


if __name__ == "__main__":
    main()
