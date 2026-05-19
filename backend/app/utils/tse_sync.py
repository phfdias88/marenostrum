"""
Importer TSE: baixa ZIP do CDN oficial, descompacta, parseia em streaming,
persiste em chunks.

Decisões críticas:
- Streaming parser (csv.DictReader linha a linha) — não carrega CSV inteiro em RAM
- Bulk insert em chunks de 5000 linhas (compromisso: latência DB vs RAM)
- Cache em /tmp/tse_cache — não re-baixa o mesmo dataset
- Limite defensivo: aborta se ZIP > 200 MB (VPS KVM 1 só tem 4GB RAM)
- Encoding latin-1 — TSE NÃO usa UTF-8 nos CSVs públicos
- Delimitador ';' — padrão TSE
- Pre-popula caches em memória: party_by_number, muni_by_tse_code,
  election_by_tse_code, candidate_by_sq → evita 1 SELECT por linha (N+1)

URLs dataset 2024:
  votacao_candidato_munzona_2024.zip → candidatos + resultados por município
  votacao_partido_munzona_2024.zip   → partidos (resumo, não precisamos pra MVP)
"""
from __future__ import annotations

import csv
import io
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import UUID, uuid4

import httpx
import structlog
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.tse import (
    Candidate,
    Election,
    Municipality,
    Party,
    SyncJobStatus,
    TseSyncJob,
    VoteResult,
)

log = structlog.get_logger("marenostrum.tse_sync")

# ---------------------------- constantes -----------------------------

TSE_BASE_URL = "https://cdn.tse.jus.br/estatistica/sead/odsele"

# Datasets suportados — chave usada em /api/v1/tse/sync?dataset=<key>
DATASETS = {
    "candidato_munzona_2024": {
        "url": f"{TSE_BASE_URL}/votacao_candidato_munzona/votacao_candidato_munzona_2024.zip",
        "year": 2024,
    },
}

CACHE_DIR = Path("/tmp/tse_cache")
MAX_ZIP_MB = 200
CHUNK_SIZE = 5_000  # linhas por bulk insert
DOWNLOAD_TIMEOUT_S = 600  # 10min — TSE pode ser lento


# ---------------------------- low-level ------------------------------


def _ensure_cache_dir() -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


def download_zip(url: str, dest: Path) -> int:
    """
    Baixa ZIP do TSE pra `dest`. Retorna tamanho em bytes.
    Aborta se > MAX_ZIP_MB (defensivo pra não esgotar disco/RAM).
    """
    log.info("tse_download_start", url=url)
    bytes_downloaded = 0
    max_bytes = MAX_ZIP_MB * 1024 * 1024

    with httpx.stream("GET", url, timeout=DOWNLOAD_TIMEOUT_S, follow_redirects=True) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=1024 * 1024):
                bytes_downloaded += len(chunk)
                if bytes_downloaded > max_bytes:
                    raise ValueError(
                        f"ZIP excede {MAX_ZIP_MB}MB (downloaded {bytes_downloaded // (1024*1024)}MB) — abortando"
                    )
                f.write(chunk)

    log.info("tse_download_complete", bytes=bytes_downloaded, dest=str(dest))
    return bytes_downloaded


def iter_csv_rows(zip_path: Path) -> Iterator[tuple[str, dict[str, str]]]:
    """
    Iterador (filename, row_dict) sobre TODOS os CSVs dentro do ZIP.
    Stream: não carrega o ZIP inteiro em memória.
    """
    with zipfile.ZipFile(zip_path) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        log.info("tse_csv_files_found", count=len(csv_names), names=csv_names[:5])

        for csv_name in csv_names:
            # latin-1 é universal pra TSE; ';' é o delimitador
            with zf.open(csv_name) as raw:
                text = io.TextIOWrapper(raw, encoding="latin-1", newline="")
                reader = csv.DictReader(text, delimiter=";")
                for row in reader:
                    yield csv_name, row


# ---------------------------- helpers --------------------------------


def _i(value: Any) -> int:
    """Converte campo TSE pra int. Retorna 0 se vazio/inválido."""
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return 0


def _s(value: Any, max_len: int = 200) -> str:
    """Limpa string TSE, trunca se necessário."""
    return str(value or "").strip()[:max_len]


# ------------------------ orchestrator -------------------------------


def run_sync_job(job_id: UUID) -> None:
    """
    Entry point pro BackgroundTask. Abre sessão DB própria.

    1. Marca job como RUNNING
    2. Baixa ZIP (com cache)
    3. Streaming parse + bulk insert em chunks
    4. Marca job como COMPLETED ou FAILED
    """
    with SessionLocal() as db:
        job = db.get(TseSyncJob, job_id)
        if job is None:
            log.error("tse_sync_job_not_found", job_id=str(job_id))
            return

        dataset_meta = DATASETS.get(job.dataset)
        if dataset_meta is None:
            _fail(db, job, f"Dataset desconhecido: {job.dataset}")
            return

        job.status = SyncJobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        db.commit()

        try:
            _ensure_cache_dir()
            zip_path = CACHE_DIR / f"{job.dataset}.zip"

            # Cache: re-usa se já baixou (TSE não muda dataset histórico)
            if not zip_path.exists():
                download_zip(dataset_meta["url"], zip_path)
            else:
                log.info("tse_zip_from_cache", path=str(zip_path))

            _process_candidato_munzona(db, job, zip_path)

            job.status = SyncJobStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            log.info(
                "tse_sync_completed",
                job_id=str(job_id),
                candidates=job.candidates_imported,
                vote_results=job.vote_results_imported,
            )

        except Exception as exc:
            log.exception("tse_sync_failed", job_id=str(job_id))
            _fail(db, job, f"{type(exc).__name__}: {exc}")


def _fail(db: Session, job: TseSyncJob, message: str) -> None:
    """
    Marca o job como FAILED.

    IMPORTANTE: a session pode estar em estado de transação abortada
    (caso o erro tenha ocorrido dentro de um db.execute(...)). Antes de
    persistir o estado FAILED, fazemos rollback + re-fetch do job, senão
    o commit final estoura "current transaction is aborted".
    """
    db.rollback()
    # Re-fetch porque o rollback pode ter desreferenciado o objeto
    job = db.get(TseSyncJob, job.id) or job
    job.status = SyncJobStatus.FAILED
    job.error_message = message[:4000]  # protege contra mensagens gigantes
    job.completed_at = datetime.now(timezone.utc)
    db.commit()


# ---------- core: parser do dataset votacao_candidato_munzona --------


def _process_candidato_munzona(
    db: Session, job: TseSyncJob, zip_path: Path,
) -> None:
    """
    Parseia o dataset `votacao_candidato_munzona_2024.zip` em streaming.

    Estratégia:
    - Pre-carrega caches: {tse_code → id} pra Election, Party, Municipality,
      Candidate. Tudo cabe em RAM (centenas a milhares de itens).
    - Pra cada linha do CSV:
      * Se Election/Party/Municipality/Candidate novo → adiciona ao buffer
        de "to-insert"; flush a cada CHUNK_SIZE.
      * VoteResult: agrega (candidate, municipality) → soma de votos.
        Flush no final.
    """
    # Caches em memória — populados do DB existente + atualizados durante parse
    elections_by_tse: dict[int, UUID] = {
        e.tse_code: e.id for e in db.execute(select(Election)).scalars()
    }
    parties_by_number: dict[int, UUID] = {
        p.number: p.id for p in db.execute(select(Party)).scalars()
    }
    munis_by_tse: dict[int, UUID] = {
        m.tse_code: m.id for m in db.execute(select(Municipality)).scalars()
    }
    candidates_by_sq: dict[int, UUID] = {
        c.sq_candidato: c.id for c in db.execute(select(Candidate)).scalars()
    }

    # Vote results agregado em memória: (candidate_id, municipality_id) → votes
    vote_acc: dict[tuple[UUID, UUID], int] = {}

    # Buffers a inserir
    elections_buf: list[dict] = []
    parties_buf: list[dict] = []
    munis_buf: list[dict] = []
    candidates_buf: list[dict] = []

    now = datetime.now(timezone.utc)
    rows_processed = 0

    for csv_name, row in iter_csv_rows(zip_path):
        rows_processed += 1

        # ---------- Election ----------
        election_code = _i(row.get("CD_ELEICAO"))
        if election_code and election_code not in elections_by_tse:
            eid = uuid4()
            elections_by_tse[election_code] = eid
            elections_buf.append({
                "id": eid,
                "tse_code": election_code,
                "year": _i(row.get("ANO_ELEICAO")),
                "round": _i(row.get("NR_TURNO")) or 1,
                "name": _s(row.get("DS_ELEICAO"), 180),
                "type_name": _s(row.get("NM_TIPO_ELEICAO"), 80),
                "created_at": now,
                "updated_at": now,
            })

        # ---------- Party ----------
        party_number = _i(row.get("NR_PARTIDO"))
        if party_number and party_number not in parties_by_number:
            pid = uuid4()
            parties_by_number[party_number] = pid
            parties_buf.append({
                "id": pid,
                "number": party_number,
                "abbreviation": _s(row.get("SG_PARTIDO"), 20),
                "name": _s(row.get("NM_PARTIDO"), 180),
                "created_at": now,
                "updated_at": now,
            })

        # ---------- Municipality ----------
        muni_code = _i(row.get("CD_MUNICIPIO"))
        if muni_code and muni_code not in munis_by_tse:
            mid = uuid4()
            munis_by_tse[muni_code] = mid
            munis_buf.append({
                "id": mid,
                "tse_code": muni_code,
                "name": _s(row.get("NM_MUNICIPIO"), 120),
                "state": _s(row.get("SG_UF"), 2).upper(),
                "created_at": now,
                "updated_at": now,
            })

        # ---------- Candidate ----------
        sq = _i(row.get("SQ_CANDIDATO"))
        if sq and sq not in candidates_by_sq and party_number and election_code:
            cid = uuid4()
            candidates_by_sq[sq] = cid
            candidates_buf.append({
                "id": cid,
                "sq_candidato": sq,
                "election_id": elections_by_tse[election_code],
                "number": _i(row.get("NR_CANDIDATO")),
                "name": _s(row.get("NM_CANDIDATO"), 180),
                "urn_name": _s(row.get("NM_URNA_CANDIDATO"), 180),
                "party_id": parties_by_number[party_number],
                "office_code": _i(row.get("CD_CARGO")),
                "office_name": _s(row.get("DS_CARGO"), 40),
                "state": _s(row.get("SG_UF"), 2).upper(),
                "situation": _s(row.get("DS_SITUACAO_CANDIDATURA"), 40),
                "created_at": now,
                "updated_at": now,
            })

        # ---------- VoteResult (agregação) ----------
        if sq and muni_code and sq in candidates_by_sq and muni_code in munis_by_tse:
            key = (candidates_by_sq[sq], munis_by_tse[muni_code])
            votes = _i(row.get("QT_VOTOS_NOMINAIS"))
            vote_acc[key] = vote_acc.get(key, 0) + votes

        # Flush periódico — economiza RAM
        if rows_processed % CHUNK_SIZE == 0:
            _flush_dim_buffers(
                db, elections_buf, parties_buf, munis_buf, candidates_buf,
                job, rows_processed,
            )

    # Flush final dos buffers
    _flush_dim_buffers(
        db, elections_buf, parties_buf, munis_buf, candidates_buf,
        job, rows_processed,
    )

    # Flush vote results — todos de uma vez no fim (cabem em RAM como dict)
    _flush_vote_results(db, vote_acc, job)


def _flush_dim_buffers(
    db: Session,
    elections_buf: list[dict],
    parties_buf: list[dict],
    munis_buf: list[dict],
    candidates_buf: list[dict],
    job: TseSyncJob,
    rows_processed: int,
) -> None:
    """Insere buffers dimensionais (election/party/muni/candidate) e limpa."""
    if elections_buf:
        db.execute(insert(Election), elections_buf)
        job.parties_imported += 0  # elections nao tem campo proprio no job — ok
        elections_buf.clear()

    if parties_buf:
        db.execute(insert(Party), parties_buf)
        job.parties_imported += len(parties_buf)
        parties_buf.clear()

    if munis_buf:
        db.execute(insert(Municipality), munis_buf)
        job.municipalities_imported += len(munis_buf)
        munis_buf.clear()

    if candidates_buf:
        db.execute(insert(Candidate), candidates_buf)
        job.candidates_imported += len(candidates_buf)
        candidates_buf.clear()

    job.rows_processed = rows_processed
    db.commit()


def _flush_vote_results(
    db: Session,
    vote_acc: dict[tuple[UUID, UUID], int],
    job: TseSyncJob,
) -> None:
    """Insere agregação final de votos em chunks."""
    now = datetime.now(timezone.utc)
    rows = [
        {
            "id": uuid4(),
            "candidate_id": cid,
            "municipality_id": mid,
            "votes": votes,
            "created_at": now,
            "updated_at": now,
        }
        for (cid, mid), votes in vote_acc.items()
    ]

    # Insere em chunks de 5k pra não estourar query size
    for i in range(0, len(rows), CHUNK_SIZE):
        chunk = rows[i : i + CHUNK_SIZE]
        db.execute(insert(VoteResult), chunk)
        job.vote_results_imported += len(chunk)
        db.commit()
        log.info(
            "tse_vote_results_flush",
            inserted=job.vote_results_imported,
            total=len(rows),
        )
