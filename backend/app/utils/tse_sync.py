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
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.tse import (
    Candidate,
    Election,
    Municipality,
    Party,
    SyncJobStatus,
    TseSectionVote,
    TseSyncJob,
    TseVotingPlace,
    VoteResult,
)

# UFs do Brasil — usado pra gerar entries no DATASETS dict
ALL_UFS = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
    "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
    "RS", "RO", "RR", "SC", "SP", "SE", "TO",
]

log = structlog.get_logger("marenostrum.tse_sync")

# ---------------------------- constantes -----------------------------

TSE_BASE_URL = "https://cdn.tse.jus.br/estatistica/sead/odsele"

# Datasets suportados — chave usada em /api/v1/tse/sync?dataset=<key>
# 'processor': nome da funcao que parseia este dataset (despachada via _PROCESSORS)
DATASETS: dict[str, dict] = {
    "candidato_munzona_2024": {
        "url": f"{TSE_BASE_URL}/votacao_candidato_munzona/votacao_candidato_munzona_2024.zip",
        "year": 2024,
        "processor": "candidato_munzona",
    },
    "candidato_munzona_2022": {
        "url": f"{TSE_BASE_URL}/votacao_candidato_munzona/votacao_candidato_munzona_2022.zip",
        "year": 2022,
        "processor": "candidato_munzona",
    },
    "locais_votacao_2024": {
        "url": f"{TSE_BASE_URL}/eleitorado_locais_votacao/eleitorado_local_votacao_2024.zip",
        "year": 2024,
        "processor": "locais_votacao",
    },
}

# Gera entries votacao_secao_2024_<UF> automaticamente — 27 UFs
for _uf in ALL_UFS:
    DATASETS[f"votacao_secao_2024_{_uf}"] = {
        "url": f"{TSE_BASE_URL}/votacao_secao/votacao_secao_2024_{_uf}.zip",
        "year": 2024,
        "processor": "votacao_secao",
        "uf": _uf,
    }

CACHE_DIR = Path("/tmp/tse_cache")
MAX_ZIP_MB = 700  # candidato_munzona_2022 tem 583MB
CHUNK_SIZE = 5_000  # linhas por bulk insert
# Flush parcial do vote_acc quando passar disso (evita OOM no container 768MB).
# 800k chaves × ~80B ≈ 64MB no dict — folga confortavel.
VOTE_ACC_MAX = 800_000
DOWNLOAD_TIMEOUT_S = 1800  # 30min — 2022 e' grande


# ---------------------------- low-level ------------------------------


def _ensure_cache_dir() -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


def download_zip(url: str, dest: Path, max_mb: int | None = None) -> int:
    """
    Baixa ZIP do TSE pra `dest`. Retorna tamanho em bytes.
    Aborta se > max_mb (default MAX_ZIP_MB) — defensivo pra não esgotar disco.
    Datasets grandes (prestacao de contas ~1.2GB) passam max_mb maior.
    """
    log.info("tse_download_start", url=url)
    bytes_downloaded = 0
    limit_mb = max_mb or MAX_ZIP_MB
    max_bytes = limit_mb * 1024 * 1024

    with httpx.stream("GET", url, timeout=DOWNLOAD_TIMEOUT_S, follow_redirects=True) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=1024 * 1024):
                bytes_downloaded += len(chunk)
                if bytes_downloaded > max_bytes:
                    raise ValueError(
                        f"ZIP excede {limit_mb}MB (downloaded {bytes_downloaded // (1024*1024)}MB) — abortando"
                    )
                f.write(chunk)

    log.info("tse_download_complete", bytes=bytes_downloaded, dest=str(dest))
    return bytes_downloaded


def iter_csv_rows(
    zip_path: Path, *, name_contains: str | None = None,
) -> Iterator[tuple[str, dict[str, str]]]:
    """
    Iterador (filename, row_dict) sobre os CSVs dentro do ZIP.
    Stream: não carrega o ZIP inteiro em memória.

    `name_contains`: se informado, processa SO os CSVs cujo nome contem essa
    substring (case-insensitive). CRITICO pro votacao_candidato_munzona, que
    inclui tanto `_BRASIL.csv` quanto `_<UF>.csv` (mesmos dados duplicados) —
    sem filtro, cada voto e contado 2x.
    """
    with zipfile.ZipFile(zip_path) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if name_contains:
            needle = name_contains.lower()
            csv_names = [n for n in csv_names if needle in n.lower()]
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

            # Despacha pro processor adequado
            processor = dataset_meta.get("processor", "candidato_munzona")
            if processor == "candidato_munzona":
                _process_candidato_munzona(db, job, zip_path)
            elif processor == "locais_votacao":
                _process_locais_votacao(db, job, zip_path)
            elif processor == "votacao_secao":
                _process_votacao_secao(
                    db, job, zip_path, uf=dataset_meta["uf"],
                )
            else:
                _fail(db, job, f"Processor desconhecido: {processor}")
                return

            job.status = SyncJobStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc)
            db.commit()

            # Dados mudaram → invalida cache de agregações (party-perf, counts, etc)
            try:
                from app.utils.agg_cache import clear_agg_cache

                clear_agg_cache()
            except Exception:
                pass
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

    # CRITICO: so o arquivo _BRASIL.csv — o ZIP tambem tem 1 csv por UF com
    # os MESMOS dados, o que duplicaria todos os votos (2x).
    for csv_name, row in iter_csv_rows(zip_path, name_contains="_BRASIL"):
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
                "result_status": _s(row.get("DS_SIT_TOT_TURNO"), 40) or None,
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

        # Flush parcial do vote_acc quando crescer demais — CRITICO pra 2022
        # (deputados x municipios geram milhoes de chaves; sem isso, OOM no
        # container de 768MB). Usa upsert-add, entao agregacao parcial e segura.
        if len(vote_acc) >= VOTE_ACC_MAX:
            # garante que candidatos referenciados ja foram inseridos
            _flush_dim_buffers(
                db, elections_buf, parties_buf, munis_buf, candidates_buf,
                job, rows_processed,
            )
            _flush_vote_results(db, vote_acc, job)
            vote_acc.clear()

    # Flush final dos buffers
    _flush_dim_buffers(
        db, elections_buf, parties_buf, munis_buf, candidates_buf,
        job, rows_processed,
    )

    # Flush final do vote_acc remanescente
    _flush_vote_results(db, vote_acc, job)
    vote_acc.clear()


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
    """
    Grava votos via UPSERT-ADD (votes = votes + excluded.votes).

    Por que upsert-add: pra datasets grandes (2022) o vote_acc e' flushado
    PARCIALMENTE varias vezes durante o parse. A mesma (candidate, municipio)
    pode aparecer em flushes diferentes (zonas processadas em momentos
    distintos) — o upsert-add soma corretamente. Pre-condicao: TRUNCATE
    tse_vote_results antes de re-importar (senao soma sobre dado antigo).
    """
    if not vote_acc:
        return
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

    for i in range(0, len(rows), CHUNK_SIZE):
        chunk = rows[i : i + CHUNK_SIZE]
        stmt = pg_insert(VoteResult.__table__).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=["candidate_id", "municipality_id"],
            set_={
                "votes": VoteResult.__table__.c.votes + stmt.excluded.votes,
                "updated_at": now,
            },
        )
        db.execute(stmt)
        job.vote_results_imported += len(chunk)
        db.commit()
        log.info(
            "tse_vote_results_flush",
            inserted=job.vote_results_imported,
            chunk=len(chunk),
        )


# ====================================================================
# Processor: locais_votacao (eleitorado_local_votacao_2024.zip)
# ====================================================================


def _process_locais_votacao(
    db: Session, job: TseSyncJob, zip_path: Path,
) -> None:
    """
    Parseia eleitorado_local_votacao_2024.csv.
    Cada linha = uma SECAO. Agregamos por (municipio, local_code) — bairro
    e endereco sao do local, nao da secao. electors_total = SUM secoes.

    Esquema das colunas relevantes:
      CD_MUNICIPIO, NR_LOCAL_VOTACAO, NM_LOCAL_VOTACAO, DS_ENDERECO,
      NM_BAIRRO, NR_LATITUDE, NR_LONGITUDE, QT_ELEITOR_SECAO
    """
    # Cache: tse_code → municipality_id
    munis_by_tse: dict[int, UUID] = {
        m.tse_code: m.id for m in db.execute(select(Municipality)).scalars()
    }

    # Cache em memoria: (municipality_id, local_code) → dict do local
    places_acc: dict[tuple[UUID, int], dict] = {}
    rows_processed = 0

    for _, row in iter_csv_rows(zip_path):
        rows_processed += 1
        muni_code = _i(row.get("CD_MUNICIPIO"))
        local_code = _i(row.get("NR_LOCAL_VOTACAO"))
        if not muni_code or not local_code:
            continue
        muni_id = munis_by_tse.get(muni_code)
        if muni_id is None:
            continue  # municipio nao importado ainda

        key = (muni_id, local_code)
        electors = _i(row.get("QT_ELEITOR_SECAO"))

        if key in places_acc:
            places_acc[key]["electors_total"] += electors
            continue

        lat = _to_float(row.get("NR_LATITUDE"))
        lng = _to_float(row.get("NR_LONGITUDE"))
        places_acc[key] = {
            "id": uuid4(),
            "local_code": local_code,
            "municipality_id": muni_id,
            "name": _s(row.get("NM_LOCAL_VOTACAO"), 200),
            "address": _s(row.get("DS_ENDERECO"), 300) or None,
            "neighborhood": _s(row.get("NM_BAIRRO"), 120) or None,
            "latitude": lat,
            "longitude": lng,
            "electors_total": electors,
        }

        if rows_processed % 20000 == 0:
            job.rows_processed = rows_processed
            db.commit()
            log.info(
                "tse_locais_progress",
                rows=rows_processed,
                unique_places=len(places_acc),
            )

    now = datetime.now(timezone.utc)
    rows = [
        {**v, "created_at": now, "updated_at": now} for v in places_acc.values()
    ]
    log.info("tse_locais_inserting", total_places=len(rows))

    for i in range(0, len(rows), CHUNK_SIZE):
        chunk = rows[i : i + CHUNK_SIZE]
        db.execute(insert(TseVotingPlace), chunk)
        db.commit()
        # Reusa campos do job pra reportar progresso (apesar do nome)
        job.municipalities_imported = len(rows[: i + len(chunk)])
        db.commit()

    job.rows_processed = rows_processed
    db.commit()
    log.info("tse_locais_done", places=len(rows), rows=rows_processed)


def _to_float(value) -> float | None:
    try:
        v = float(str(value).strip().replace(",", "."))
        if -90 <= v <= 90 or -180 <= v <= 180:
            return v
    except (ValueError, TypeError, AttributeError):
        pass
    return None


# ====================================================================
# Processor: votacao_secao_<UF> (votacao_secao_2024_<UF>.zip)
# ====================================================================


def _process_votacao_secao(
    db: Session, job: TseSyncJob, zip_path: Path, *, uf: str,
) -> None:
    """
    Parseia votacao_secao_2024_<UF>.csv. Cada linha = (candidato, secao, votos).
    Agregamos por (candidate_id, voting_place_id) → SUM(votos).

    Colunas relevantes: SQ_CANDIDATO, CD_MUNICIPIO, NR_LOCAL_VOTACAO, QT_VOTOS

    Pre-condicao: locais_votacao_2024 ja sincronizado (precisamos do mapping
    (muni, local_code) → voting_place_id) E candidatos do UF ja sincronizados.
    """
    # Cache 1: SQ_CANDIDATO → candidate_id (pre-filtrado por UF pra economizar RAM)
    candidates_by_sq: dict[int, UUID] = {
        c.sq_candidato: c.id
        for c in db.execute(
            select(Candidate).where(Candidate.state == uf)
        ).scalars()
    }
    log.info("tse_secao_candidates_loaded", uf=uf, count=len(candidates_by_sq))

    # Cache 2: (municipality_id, local_code) → voting_place_id (so do UF)
    munis_by_tse: dict[int, UUID] = {
        m.tse_code: m.id for m in db.execute(
            select(Municipality).where(Municipality.state == uf)
        ).scalars()
    }
    voting_places_lookup: dict[tuple[UUID, int], UUID] = {}
    for vp in db.execute(
        select(TseVotingPlace).where(
            TseVotingPlace.municipality_id.in_(list(munis_by_tse.values()))
        )
    ).scalars():
        voting_places_lookup[(vp.municipality_id, vp.local_code)] = vp.id
    log.info(
        "tse_secao_places_loaded", uf=uf, count=len(voting_places_lookup),
    )

    if not voting_places_lookup:
        raise RuntimeError(
            f"Nenhum tse_voting_places pra UF={uf}. Rode locais_votacao_2024 antes."
        )

    # Agregacao em memoria: (candidate_id, voting_place_id) → votes
    # Estimativa MG: ~8k locais × ~150 candidates = ~1.2M entries. Cabe.
    votes_acc: dict[tuple[UUID, UUID], int] = {}
    rows_processed = 0
    skipped = 0

    for _, row in iter_csv_rows(zip_path):
        rows_processed += 1
        sq = _i(row.get("SQ_CANDIDATO"))
        muni_code = _i(row.get("CD_MUNICIPIO"))
        local_code = _i(row.get("NR_LOCAL_VOTACAO"))
        votes = _i(row.get("QT_VOTOS"))

        cand_id = candidates_by_sq.get(sq)
        muni_id = munis_by_tse.get(muni_code)
        if cand_id is None or muni_id is None or not local_code:
            skipped += 1
            continue
        vp_id = voting_places_lookup.get((muni_id, local_code))
        if vp_id is None:
            skipped += 1
            continue

        key = (cand_id, vp_id)
        votes_acc[key] = votes_acc.get(key, 0) + votes

        if rows_processed % 100_000 == 0:
            log.info(
                "tse_secao_progress",
                uf=uf,
                rows=rows_processed,
                aggregated=len(votes_acc),
                skipped=skipped,
            )
            job.rows_processed = rows_processed
            db.commit()

    log.info(
        "tse_secao_parsed",
        uf=uf,
        rows=rows_processed,
        aggregated=len(votes_acc),
        skipped=skipped,
    )

    # Insercao em chunks. Como pode rodar 2x (re-import), usamos
    # ON CONFLICT DO UPDATE pra ser idempotente.
    now = datetime.now(timezone.utc)
    rows_out = [
        {
            "id": uuid4(),
            "candidate_id": cid,
            "voting_place_id": vp,
            "votes": v,
            "created_at": now,
            "updated_at": now,
        }
        for (cid, vp), v in votes_acc.items()
    ]

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    for i in range(0, len(rows_out), CHUNK_SIZE):
        chunk = rows_out[i : i + CHUNK_SIZE]
        stmt = pg_insert(TseSectionVote.__table__).values(chunk)
        # Upsert: re-rodar a UF sobrescreve votos (caso TSE atualize dataset)
        stmt = stmt.on_conflict_do_update(
            index_elements=["candidate_id", "voting_place_id"],
            set_={"votes": stmt.excluded.votes, "updated_at": now},
        )
        db.execute(stmt)
        db.commit()
        job.vote_results_imported = i + len(chunk)
        db.commit()
        if (i // CHUNK_SIZE) % 5 == 0:
            log.info(
                "tse_secao_inserted",
                uf=uf,
                inserted=job.vote_results_imported,
                total=len(rows_out),
            )

    job.rows_processed = rows_processed
    db.commit()
    log.info("tse_secao_done", uf=uf, total=len(rows_out))
