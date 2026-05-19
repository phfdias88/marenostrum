"""
One-shot: popula latitude/longitude em tse_municipalities a partir do
dataset publico CC0 kelvins/Municipios-Brasileiros (todos 5570 municipios
do Brasil com coords IBGE).

Uso:
    docker compose exec api python -m app.utils.tse_muni_geocode

Estrategia:
- Download do CSV publico (~500KB, fica em /tmp/muni_coords.csv).
- Normaliza nomes (lower, sem acentos) pra fazer match com nossos
  tse_municipalities.
- Bulk UPDATE em lote.

Fonte: https://github.com/kelvins/Municipios-Brasileiros (licenca CC0)
"""
from __future__ import annotations

import csv
import io
import logging
import unicodedata
from typing import Iterable

import httpx
import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.tse import Municipality

log = structlog.get_logger("marenostrum.muni_geocode")

KELVINS_CSV_URL = (
    "https://raw.githubusercontent.com/kelvins/Municipios-Brasileiros/"
    "main/csv/municipios.csv"
)

# Mapping codigo_uf -> sigla UF (tabela fixa do IBGE)
UF_BY_CODE: dict[int, str] = {
    11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO",
    21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL",
    28: "SE", 29: "BA",
    31: "MG", 32: "ES", 33: "RJ", 35: "SP",
    41: "PR", 42: "SC", 43: "RS",
    50: "MS", 51: "MT", 52: "GO", 53: "DF",
}


def _normalize(s: str) -> str:
    """Normaliza pra comparacao: lower, sem acentos, sem espacos extras."""
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    # Remove caracteres especiais (mantem letras/numeros/espaco/hifen)
    return " ".join(s.split())


def _download_csv() -> str:
    log.info("muni_geocode_download_start", url=KELVINS_CSV_URL)
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        r = client.get(KELVINS_CSV_URL)
        r.raise_for_status()
    log.info("muni_geocode_download_complete", bytes=len(r.content))
    return r.text


def _parse_csv(csv_text: str) -> dict[tuple[str, str], tuple[float, float]]:
    """
    Retorna {(nome_normalizado, UF): (lat, lng)}.
    Colunas esperadas: codigo_ibge, nome, latitude, longitude, capital,
                       codigo_uf, siafi_id, ddd, fuso_horario
    """
    coords: dict[tuple[str, str], tuple[float, float]] = {}
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        try:
            uf_code = int(row["codigo_uf"])
            uf = UF_BY_CODE.get(uf_code)
            if not uf:
                continue
            lat = float(row["latitude"])
            lng = float(row["longitude"])
        except (ValueError, KeyError):
            continue
        key = (_normalize(row["nome"]), uf)
        coords[key] = (lat, lng)
    log.info("muni_geocode_parsed", entries=len(coords))
    return coords


def populate(db: Session, *, dry_run: bool = False) -> dict[str, int]:
    """
    Popula tse_municipalities.latitude/longitude.
    Retorna {matched, unmatched, total}.
    """
    csv_text = _download_csv()
    lookup = _parse_csv(csv_text)

    # Le todos os municipios TSE
    munis = db.query(Municipality).all()
    total = len(munis)
    matched = 0
    unmatched_examples: list[str] = []

    updates: list[dict] = []
    for m in munis:
        key = (_normalize(m.name), m.state)
        coord = lookup.get(key)
        if coord is None:
            if len(unmatched_examples) < 10:
                unmatched_examples.append(f"{m.name}/{m.state}")
            continue
        lat, lng = coord
        if m.latitude == lat and m.longitude == lng:
            continue  # ja igual, skip
        updates.append({"id": m.id, "lat": lat, "lng": lng})
        matched += 1

    log.info(
        "muni_geocode_match",
        total=total,
        matched=matched,
        unmatched=total - matched,
        unmatched_examples=unmatched_examples[:10],
    )

    if dry_run:
        return {"matched": matched, "unmatched": total - matched, "total": total}

    # Bulk update via Core text SQL + executemany (mais simples e robusto que
    # ORM bulk update, que estava com issue com UUID PK em SQLAlchemy 2.0).
    if updates:
        CHUNK = 2000
        stmt = text(
            "UPDATE tse_municipalities "
            "SET latitude = :lat, longitude = :lng, updated_at = now() "
            "WHERE id = :id"
        )
        for i in range(0, len(updates), CHUNK):
            chunk = updates[i : i + CHUNK]
            db.execute(stmt, chunk)
            db.commit()
            log.info("muni_geocode_chunk_done", chunk_size=len(chunk))

    return {"matched": matched, "unmatched": total - matched, "total": total}


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as db:
        result = populate(db)
    print("Resultado:", result)


if __name__ == "__main__":
    main()
