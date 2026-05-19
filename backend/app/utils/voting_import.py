"""
Parser de CSV de locais de votação.

Aceita o formato típico exportado por software político BR:
    Local de Votação;Endereço;Bairro;Município;Latitude;Longitude;Votos

Igual ao csv_import (de contatos), aqui detectamos encoding (utf-8-sig +
fallback latin-1) e dialeto (',' ou ';') automaticamente.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from typing import Any

# Mapa de cabecalhos → campo do model VotingPlace
_HEADER_MAP: dict[str, str] = {
    "nome": "name",
    "local": "name",
    "localdevotacao": "name",
    "localdevotação": "name",  # com acento
    "endereco": "address",
    "endereço": "address",
    "bairro": "neighborhood",
    "cidade": "city",
    "municipio": "city",
    "município": "city",
    "uf": "state",
    "estado": "state",
    "latitude": "latitude",
    "lat": "latitude",
    "longitude": "longitude",
    "lng": "longitude",
    "lon": "longitude",
    "long": "longitude",
    "votos": "votes",
    "eleitorado": "total_voters",
    "totaleleitores": "total_voters",
    "tsecode": "tse_code",
    "codigotse": "tse_code",
    "observacoes": "notes",
    "observações": "notes",
    "obs": "notes",
}


def _normalize_key(s: str) -> str:
    """'Local de Votação' -> 'localdevotacao' (sem acento, sem espaço, lowercase)."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[\s_-]+", "", s).lower().strip()


def _clean(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _parse_int(v: str) -> int | None:
    try:
        return int(v.replace(".", "").replace(",", ""))
    except ValueError:
        return None


def _parse_float(v: str) -> float | None:
    try:
        return float(v.replace(",", "."))
    except ValueError:
        return None


def decode_csv(file_bytes: bytes) -> str:
    try:
        return file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return file_bytes.decode("latin-1")


def parse_voting_csv(
    file_bytes: bytes,
    *,
    default_election_year: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """
    Retorna (rows_validas, erros).

    Cada row valida tem: name, address, neighborhood, city, state, latitude,
    longitude, votes, total_voters, election_year, tse_code, notes.
    """
    text = decode_csv(file_bytes)

    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    errors: list[dict[str, str]] = []

    if not reader.fieldnames:
        return [], [{"row": "1", "message": "CSV vazio ou sem cabeçalho"}]

    field_for_col = {col: _HEADER_MAP.get(_normalize_key(col)) for col in reader.fieldnames}

    # Mínimo: ter coluna 'nome' (ou local de votação)
    if "name" not in field_for_col.values():
        return [], [{
            "row": "1",
            "message": "CSV precisa ter coluna 'Nome' ou 'Local de Votação'",
        }]

    rows: list[dict[str, Any]] = []
    for line_num, raw in enumerate(reader, start=2):
        try:
            row = _normalize_row(
                raw, field_for_col, default_election_year=default_election_year,
            )
        except ValueError as exc:
            errors.append({"row": str(line_num), "message": str(exc)})
            continue
        rows.append(row)

    return rows, errors


def _normalize_row(
    raw: dict[str, str],
    field_for_col: dict[str, str | None],
    *,
    default_election_year: int | None,
) -> dict[str, Any]:
    data: dict[str, Any] = {}

    for col, value in raw.items():
        field = field_for_col.get(col)
        if field is None:
            continue
        cleaned = _clean(value)
        if cleaned is None:
            continue

        if field == "votes":
            n = _parse_int(cleaned)
            data["votes"] = n if n is not None else 0
        elif field == "total_voters":
            n = _parse_int(cleaned)
            if n is not None:
                data["total_voters"] = n
        elif field in ("latitude", "longitude"):
            v = _parse_float(cleaned)
            if v is None:
                raise ValueError(f"{field} inválido: '{cleaned}'")
            if field == "latitude" and not (-90 <= v <= 90):
                raise ValueError(f"latitude fora do range: {v}")
            if field == "longitude" and not (-180 <= v <= 180):
                raise ValueError(f"longitude fora do range: {v}")
            data[field] = v
        elif field == "state":
            if len(cleaned) != 2:
                raise ValueError(f"UF deve ter 2 letras: '{cleaned}'")
            data["state"] = cleaned.upper()
        else:
            # Strings simples: name, address, neighborhood, city, tse_code, notes
            data[field] = cleaned

    # Default
    data.setdefault("votes", 0)
    if default_election_year is not None and "election_year" not in data:
        data["election_year"] = default_election_year

    if not data.get("name"):
        raise ValueError("Nome do local ausente")

    return data
