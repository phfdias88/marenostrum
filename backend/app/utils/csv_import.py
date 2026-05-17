"""
Parser de CSV de contatos.

Decisoes:
- ENCODING: tenta utf-8-sig (cobre UTF-8 com/sem BOM — Excel pt-BR salva com BOM),
  fallback latin-1 (Excel BR legado). Latin-1 nunca falha em decode.
- DIALETO: csv.Sniffer detecta automaticamente delimitador (',' vs ';').
  Excel pt-BR usa ';' por default; admin gringo usa ','. Cobrimos os dois.
- CABECALHOS: normalizados (lowercase + sem acento + sem espaco) antes de
  mapear. Usuario pode digitar 'Nome', 'NOME', 'nome', 'Nome ' — tudo bate.

Saida: lista de dicts JA pronta para o ContactRepository.bulk_create, e uma
lista de erros por linha (linha 2+ = primeira linha de dados).
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from datetime import date, datetime
from typing import Any

from app.models.contact import ContactType
from app.schemas.contact import ImportRowError

# ----------------------------- column mapping -----------------------------

# Chaves: nome normalizado (lower, sem acento, sem espaco).
# Valores: nome do campo no model SQLAlchemy.
HEADER_MAP: dict[str, str] = {
    "nome": "full_name",
    "nomecompleto": "full_name",
    "telefone": "phone",
    "celular": "phone",
    "email": "email",
    "endereco": "address",
    "bairro": "neighborhood",
    "cidade": "city",
    "uf": "state",
    "estado": "state",
    "nascimento": "birth_date",
    "dataaniversario": "birth_date",
    "aniversario": "birth_date",
    "tipo": "type",
    "observacoes": "notes",
    "obs": "notes",
}

# Tipos aceitos no CSV (PT-BR ou EN) -> enum interno.
TYPE_MAP: dict[str, ContactType] = {
    "eleitor": ContactType.VOTER,
    "voter": ContactType.VOTER,
    "lideranca": ContactType.LEADER,
    "lider": ContactType.LEADER,
    "leader": ContactType.LEADER,
    "apoiador": ContactType.SUPPORTER,
    "supporter": ContactType.SUPPORTER,
    "doador": ContactType.DONOR,
    "donor": ContactType.DONOR,
    "outro": ContactType.OTHER,
    "other": ContactType.OTHER,
}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# -------------------------------- helpers ---------------------------------


def _normalize_key(s: str) -> str:
    """'Nome Completo ' -> 'nomecompleto'."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[\s_-]+", "", s).lower().strip()


def _clean(v: Any) -> str | None:
    """Trim + coerce empty/None to None."""
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _parse_birth_date(raw: str) -> date | None:
    """Aceita DD/MM/YYYY (BR) e YYYY-MM-DD (ISO). Retorna None se invalido."""
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_type(raw: str | None) -> ContactType:
    if not raw:
        return ContactType.VOTER
    return TYPE_MAP.get(_normalize_key(raw), ContactType.VOTER)


# -------------------------- main entry points -----------------------------


def decode_csv(file_bytes: bytes) -> str:
    """utf-8-sig primeiro (Excel pt-BR), fallback latin-1 (nunca falha)."""
    try:
        return file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return file_bytes.decode("latin-1")


def parse_csv(
    file_bytes: bytes,
) -> tuple[list[dict[str, Any]], list[ImportRowError]]:
    """
    Parseia CSV bruto. Retorna (rows_validas_para_insert, erros_por_linha).

    Rows validas = dicts ja prontos para passar ao bulk_create:
        {"full_name": str, "phone": str|None, "email": str|None, ...}
    Sem id, tenant_id, created_at, updated_at — o repo cuida disso.
    """
    text = decode_csv(file_bytes)

    # Sniff do dialeto (delimitador). Limita amostra a 8KB pra ser rapido.
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel  # fallback: ',' padrao

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    errors: list[ImportRowError] = []

    if not reader.fieldnames:
        return [], [ImportRowError(row=1, message="CSV vazio ou sem cabecalho")]

    # Mapeia cada coluna do CSV pra um campo do model (ou None se desconhecida)
    field_for_col = {col: HEADER_MAP.get(_normalize_key(col)) for col in reader.fieldnames}

    # Pelo menos a coluna "nome" precisa existir
    if "full_name" not in field_for_col.values():
        return [], [
            ImportRowError(
                row=1,
                message="CSV precisa ter ao menos a coluna 'Nome'",
            )
        ]

    rows: list[dict[str, Any]] = []
    # csv DictReader comeca em linha 2 (depois do header).
    # Header e linha 1, primeira linha de dados e 2.
    for line_num, raw in enumerate(reader, start=2):
        try:
            row = _normalize_row(raw, field_for_col)
        except ValueError as exc:
            errors.append(ImportRowError(row=line_num, message=str(exc)))
            continue
        rows.append(row)

    return rows, errors


def _normalize_row(
    raw: dict[str, str],
    field_for_col: dict[str, str | None],
) -> dict[str, Any]:
    """
    Pega uma linha bruta do CSV e devolve dict pronto pro insert.
    Levanta ValueError com mensagem amigavel se linha for invalida.
    """
    data: dict[str, Any] = {}

    for col, value in raw.items():
        field = field_for_col.get(col)
        if field is None:
            continue  # coluna nao mapeada, ignora silenciosamente
        cleaned = _clean(value)
        if cleaned is None:
            continue

        if field == "birth_date":
            parsed = _parse_birth_date(cleaned)
            if parsed is None:
                raise ValueError(
                    f"Data de nascimento invalida: '{cleaned}' (use DD/MM/AAAA)"
                )
            data["birth_date"] = parsed
        elif field == "type":
            data["type"] = _parse_type(cleaned)
        elif field == "email":
            if not _EMAIL_RE.match(cleaned):
                raise ValueError(f"Email invalido: '{cleaned}'")
            data["email"] = cleaned
        elif field == "state":
            if len(cleaned) != 2:
                raise ValueError(f"UF deve ter 2 letras: '{cleaned}'")
            data["state"] = cleaned.upper()
        else:
            data[field] = cleaned

    # Default de tipo
    data.setdefault("type", ContactType.VOTER)

    # Nome e obrigatorio
    name = data.get("full_name")
    if not name or len(name) < 2:
        raise ValueError("Nome ausente ou muito curto (minimo 2 caracteres)")

    return data
