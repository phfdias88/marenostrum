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
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import UUID, uuid4

import httpx
import structlog
from sqlalchemy import delete, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.tse import (
    Candidate,
    CandidateZoneVote,
    Election,
    Municipality,
    MunicipalityElectorate,
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
    # ---- HISTORICO LONGO (Wave 4 — 21A) ---------------------------------
    # 2020 (municipal): prefeito + vereador. ZIP ~280MB.
    "candidato_munzona_2020": {
        "url": f"{TSE_BASE_URL}/votacao_candidato_munzona/votacao_candidato_munzona_2020.zip",
        "year": 2020,
        "processor": "candidato_munzona",
        "max_mb": 500,
    },
    # 2018 (federal/estadual): pres + gov + sen + dep fed + dep est. ZIP ~450MB.
    "candidato_munzona_2018": {
        "url": f"{TSE_BASE_URL}/votacao_candidato_munzona/votacao_candidato_munzona_2018.zip",
        "year": 2018,
        "processor": "candidato_munzona",
        "max_mb": 700,
    },
    # 2016 (municipal). ZIP ~260MB.
    "candidato_munzona_2016": {
        "url": f"{TSE_BASE_URL}/votacao_candidato_munzona/votacao_candidato_munzona_2016.zip",
        "year": 2016,
        "processor": "candidato_munzona",
        "max_mb": 500,
    },
    # 2014 (federal/estadual). ZIP ~400MB.
    "candidato_munzona_2014": {
        "url": f"{TSE_BASE_URL}/votacao_candidato_munzona/votacao_candidato_munzona_2014.zip",
        "year": 2014,
        "processor": "candidato_munzona",
        "max_mb": 700,
    },
    "locais_votacao_2024": {
        "url": f"{TSE_BASE_URL}/eleitorado_locais_votacao/eleitorado_local_votacao_2024.zip",
        "year": 2024,
        "processor": "locais_votacao",
    },
    "perfil_eleitorado_2024": {
        "url": f"{TSE_BASE_URL}/perfil_eleitorado/perfil_eleitorado_2024.zip",
        "year": 2024,
        "processor": "perfil_eleitorado",
        "max_mb": 300,  # zip ~187MB
    },
    # Votos por ZONA — reprocessa o munzona guardando NR_ZONA (votos por
    # candidato × município × zona). Mesma fonte do candidato_munzona.
    "zona_votos_2024": {
        "url": f"{TSE_BASE_URL}/votacao_candidato_munzona/votacao_candidato_munzona_2024.zip",
        "year": 2024,
        "processor": "zona_votos",
    },
    "zona_votos_2022": {
        "url": f"{TSE_BASE_URL}/votacao_candidato_munzona/votacao_candidato_munzona_2022.zip",
        "year": 2022,
        "processor": "zona_votos",
        "max_mb": 700,
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

# Voto por bairro de anos anteriores (PDF item #4) — locais + seções por ANO.
# Limitado ao RJ (estado do cliente) pra não estourar o VPS. Rodar o
# locais_votacao_<ano> ANTES do votacao_secao_<ano>_<UF> (precisa do mapping).
for _yr in (2020, 2022):
    DATASETS[f"locais_votacao_{_yr}"] = {
        "url": f"{TSE_BASE_URL}/eleitorado_locais_votacao/eleitorado_local_votacao_{_yr}.zip",
        "year": _yr,
        "processor": "locais_votacao",
    }
    DATASETS[f"votacao_secao_{_yr}_RJ"] = {
        "url": f"{TSE_BASE_URL}/votacao_secao/votacao_secao_{_yr}_RJ.zip",
        "year": _yr,
        "processor": "votacao_secao",
        "uf": "RJ",
    }

# CPF dos candidatos (dataset consulta_cand do TSE) — popula tse_candidates.cpf
# (por SQ_CANDIDATO) pra agrupar candidaturas da MESMA pessoa por CPF na busca.
# 1 zip por ano, com todas as UFs.
for _yr in (2014, 2016, 2018, 2020, 2022, 2024):
    DATASETS[f"consulta_cand_{_yr}"] = {
        "url": f"{TSE_BASE_URL}/consulta_cand/consulta_cand_{_yr}.zip",
        "year": _yr,
        "processor": "consulta_cand",
        "max_mb": 600,
    }

CACHE_DIR = Path("/tmp/tse_cache")
MAX_ZIP_MB = 700  # candidato_munzona_2022 tem 583MB
CHUNK_SIZE = 5_000  # linhas por bulk insert
# Flush parcial do vote_acc quando passar disso (evita OOM).
# Reduzido de 800k -> 400k (Wave 4): datasets federais grandes (2018/2014)
# tem mais chaves (candidato×municipio) por causa de presidente em todas
# as UFs. Flush mais frequente = menor pico de RAM. ~400k × 150B ≈ 60MB.
VOTE_ACC_MAX = 400_000
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
                download_zip(dataset_meta["url"], zip_path, max_mb=dataset_meta.get("max_mb"))
            else:
                log.info("tse_zip_from_cache", path=str(zip_path))

            # Despacha pro processor adequado
            processor = dataset_meta.get("processor", "candidato_munzona")
            if processor == "candidato_munzona":
                _process_candidato_munzona(db, job, zip_path)
            elif processor == "locais_votacao":
                _process_locais_votacao(
                    db, job, zip_path, year=dataset_meta.get("year", 2024),
                )
            elif processor == "votacao_secao":
                _process_votacao_secao(
                    db, job, zip_path, uf=dataset_meta["uf"],
                    year=dataset_meta.get("year", 2024),
                )
            elif processor == "perfil_eleitorado":
                _process_perfil_eleitorado(db, job, zip_path)
            elif processor == "zona_votos":
                _process_zona_votos(db, job, zip_path, year=dataset_meta["year"])
            elif processor == "consulta_cand":
                _process_consulta_cand(db, job, zip_path)
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
    # OTIMIZACAO DE MEMORIA (Wave 4): so' carregamos candidatos do ANO sendo
    # importado. SQ_CANDIDATO e' unico por eleicao — anos diferentes nunca
    # colidem. Carregar a tabela inteira (~1M apos historico) custava ~177MB
    # de baseline e causava OOM nos datasets federais grandes (2018/2014).
    # Filtrando por job.year, anos novos comecam com dict vazio.
    _year_election_ids = [
        e.id for e in db.execute(
            select(Election.id).where(Election.year == job.year)
        ).scalars()
    ]
    if _year_election_ids:
        candidates_by_sq: dict[int, UUID] = {
            c.sq_candidato: c.id for c in db.execute(
                select(Candidate).where(Candidate.election_id.in_(_year_election_ids))
            ).scalars()
        }
    else:
        candidates_by_sq = {}

    # Vote results agregado em memória: (candidate_id, municipality_id) → votes
    vote_acc: dict[tuple[UUID, UUID], int] = {}

    # SQ_CANDIDATO → status final do 2º turno (sobrescreve "2º TURNO" no fim)
    runoff_status: dict[int, str] = {}

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

        # ---------- Status final de 2º turno ----------
        # O candidato é criado na 1ª linha vista (geralmente 1º turno, status
        # "2º TURNO"). Pra quem foi a 2º turno, o resultado REAL (ELEITO/NÃO
        # ELEITO) só está nas linhas de NR_TURNO=2. Capturamos esse status pra
        # sobrescrever no fim — senão presidente/governador eleito em 2º turno
        # fica eternamente com status "2º TURNO".
        _sq_turno = _i(row.get("SQ_CANDIDATO"))
        if _sq_turno and _i(row.get("NR_TURNO")) == 2:
            _st2 = _s(row.get("DS_SIT_TOT_TURNO"), 40) or None
            if _st2:
                runoff_status[_sq_turno] = _st2

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
        # APENAS 1º turno: a votação nominal exibida é a do 1º turno (padrão
        # TSE/imprensa). Sem este filtro, candidatos que foram a 2º turno
        # (presidente/governador/prefeito de capital) teriam votos do 1º + 2º
        # SOMADOS na mesma linha (mesmo SQ_CANDIDATO), inflando o total — ex:
        # Lula 2022 apareceria com 117M (57M 1ºT + 60M 2ºT) em vez de 57M.
        # O resultado final (ELEITO em 2º turno) já vem de runoff_status.
        _turno = _i(row.get("NR_TURNO")) or 1
        if (
            _turno == 1
            and sq and muni_code
            and sq in candidates_by_sq and muni_code in munis_by_tse
        ):
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

    # Sobrescreve o result_status dos candidatos que foram a 2º turno com o
    # resultado REAL daquele turno (ELEITO / NÃO ELEITO). Sem isso, presidente
    # ou governador eleito no 2º turno ficaria com status "2º TURNO".
    if runoff_status:
        from sqlalchemy import bindparam, update as _update

        params = [{"_sq": sq, "_st": st} for sq, st in runoff_status.items()]
        stmt = (
            _update(Candidate)
            .where(Candidate.sq_candidato == bindparam("_sq"))
            .values(result_status=bindparam("_st"))
        )
        db.execute(stmt, params)
        db.commit()
        log.info("tse_runoff_status_applied", count=len(params))


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
    db: Session, job: TseSyncJob, zip_path: Path, *, year: int = 2024,
) -> None:
    """
    Parseia eleitorado_local_votacao_2024.csv.
    Cada linha = uma SECAO. Agregamos por (municipio, local_code) — bairro
    e endereco sao do local, nao da secao. electors_total = SUM secoes.

    Esquema das colunas relevantes:
      CD_MUNICIPIO, NR_LOCAL_VOTACAO, NM_LOCAL_VOTACAO, DS_ENDERECO,
      NM_BAIRRO, NR_LATITUDE, NR_LONGITUDE, QT_ELEITOR_SECAO
    """
    # Cache: tse_code → municipality_id + centroide do município (pro fallback
    # de coordenada quando o local vem sem coord do TSE).
    munis_by_tse: dict[int, UUID] = {}
    muni_centroid_by_id: dict[UUID, tuple[float, float]] = {}
    for m in db.execute(select(Municipality)).scalars():
        munis_by_tse[m.tse_code] = m.id
        if _coord_in_brazil(m.latitude, m.longitude):
            muni_centroid_by_id[m.id] = (m.latitude, m.longitude)

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
        # TSE manda -1,-1 (ou lixo) quando o local não tem coordenada — isso
        # jogava o local "no meio do Atlântico". Cai no centroide do município
        # (cidade certa) em vez de uma coord inválida.
        if not _coord_in_brazil(lat, lng):
            centroid = muni_centroid_by_id.get(muni_id)
            lat, lng = centroid if centroid else (None, None)
        places_acc[key] = {
            "id": uuid4(),
            "year": year,
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


def _coord_in_brazil(lat, lng) -> bool:
    """Coordenada dentro da bbox do Brasil — descarta o -1,-1 (e lixo) do TSE."""
    return (
        lat is not None
        and lng is not None
        and -34 <= lat <= 6
        and -74 <= lng <= -34
    )


# ====================================================================
# Processor: consulta_cand (consulta_cand_<ano>.zip) — popula o CPF
# ====================================================================


def _process_consulta_cand(db: Session, job: TseSyncJob, zip_path: Path) -> None:
    """
    Parseia consulta_cand_<ano> (registro de candidaturas) e grava o CPF em
    tse_candidates, casando por SQ_CANDIDATO. CPF é o ID único da PESSOA entre
    eleições/cargos/UFs — é o que o agrupamento da busca usa.

    Lê só o arquivo _BRASIL (o zip tem 1 csv por UF com os mesmos dados).
    Colunas: SQ_CANDIDATO, NR_CPF_CANDIDATO.
    """
    from sqlalchemy import bindparam, update as _update

    sq_to_cpf: dict[int, str] = {}
    rows_processed = 0
    for _csv_name, row in iter_csv_rows(zip_path, name_contains="_BRASIL"):
        rows_processed += 1
        sq = _i(row.get("SQ_CANDIDATO"))
        cpf_raw = str(row.get("NR_CPF_CANDIDATO") or "")
        cpf = "".join(ch for ch in cpf_raw if ch.isdigit())
        # TSE às vezes mascara/zera o CPF — só guarda 11 dígitos plausíveis.
        if sq and len(cpf) == 11 and cpf != "00000000000":
            sq_to_cpf[sq] = cpf
        if rows_processed % 50000 == 0:
            job.rows_processed = rows_processed
            db.commit()
            log.info("tse_consulta_cand_progress", rows=rows_processed, cpfs=len(sq_to_cpf))

    # Batch UPDATE por SQ_CANDIDATO (índice único → rápido). synchronize_session
    # =None: executemany de UPDATE com WHERE exige bypass do sync da sessão ORM.
    stmt = (
        _update(Candidate)
        .where(Candidate.sq_candidato == bindparam("b_sq"))
        .values(cpf=bindparam("b_cpf"))
        .execution_options(synchronize_session=None)
    )
    items = [{"b_sq": sq, "b_cpf": cpf} for sq, cpf in sq_to_cpf.items()]
    for i in range(0, len(items), CHUNK_SIZE):
        db.execute(stmt, items[i : i + CHUNK_SIZE])
        db.commit()

    job.rows_processed = rows_processed
    db.commit()
    log.info(
        "tse_consulta_cand_done",
        rows=rows_processed,
        cpfs_encontrados=len(sq_to_cpf),
    )


# ====================================================================
# Processor: votacao_secao_<UF> (votacao_secao_2024_<UF>.zip)
# ====================================================================


def _process_votacao_secao(
    db: Session, job: TseSyncJob, zip_path: Path, *, uf: str, year: int = 2024,
) -> None:
    """
    Parseia votacao_secao_<year>_<UF>.csv. Cada linha = (candidato, secao, votos).
    Agregamos por (candidate_id, voting_place_id) → SUM(votos).

    Colunas relevantes: SQ_CANDIDATO, CD_MUNICIPIO, NR_LOCAL_VOTACAO, QT_VOTOS

    Pre-condicao: locais_votacao_<year> ja sincronizado (precisamos do mapping
    (muni, local_code) → voting_place_id daquele ANO) E candidatos do UF/ano.
    """
    # Cache 1: SQ_CANDIDATO → candidate_id (pre-filtrado por UF+ANO pra RAM e
    # pra não casar com candidato homônimo de outro ano).
    candidates_by_sq: dict[int, UUID] = {
        c.sq_candidato: c.id
        for c in db.execute(
            select(Candidate)
            .join(Election, Candidate.election_id == Election.id)
            .where(Candidate.state == uf, Election.year == year)
        ).scalars()
    }
    log.info("tse_secao_candidates_loaded", uf=uf, year=year, count=len(candidates_by_sq))

    # Cache 2: (municipality_id, local_code) → voting_place_id (só do UF, ANO certo)
    munis_by_tse: dict[int, UUID] = {
        m.tse_code: m.id for m in db.execute(
            select(Municipality).where(Municipality.state == uf)
        ).scalars()
    }
    voting_places_lookup: dict[tuple[UUID, int], UUID] = {}
    for vp in db.execute(
        select(TseVotingPlace).where(
            TseVotingPlace.municipality_id.in_(list(munis_by_tse.values())),
            TseVotingPlace.year == year,
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
        # APENAS 1º turno — senão runoff (pres/gov/prefeito de capital) soma
        # 1º + 2º turno na mesma linha (mesmo SQ), dobrando os votos por seção.
        if (_i(row.get("NR_TURNO")) or 1) != 1:
            skipped += 1
            continue
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


# ====================================================================
# Processor: perfil_eleitorado (perfil_eleitorado_2024.zip)
# ====================================================================

_AGE_ORDER = ["16-17", "18-24", "25-34", "35-44", "45-59", "60-69", "70+"]
_EDU_ORDER = [
    "Analfabeto", "Lê e escreve", "Fundamental", "Médio", "Superior",
    "Não informado",
]
_GENDER_ORDER = ["Feminino", "Masculino", "Não informado"]


def _age_bucket(ds: str) -> str:
    m = re.match(r"\s*(\d+)", ds or "")
    if not m:
        return "70+"  # "100 anos ou mais" etc caem aqui; "Inválida" é raro
    n = int(m.group(1))
    if n <= 17:
        return "16-17"
    if n <= 24:
        return "18-24"
    if n <= 34:
        return "25-34"
    if n <= 44:
        return "35-44"
    if n <= 59:
        return "45-59"
    if n <= 69:
        return "60-69"
    return "70+"


def _edu_bucket(ds: str) -> str:
    s = (ds or "").upper()
    if "ANALFABETO" in s:
        return "Analfabeto"
    if "LÊ E ESCREVE" in s or "LE E ESCREVE" in s:
        return "Lê e escreve"
    if "FUNDAMENTAL" in s or "1º GRAU" in s or "1O GRAU" in s:
        return "Fundamental"
    if "MÉDIO" in s or "MEDIO" in s or "2º GRAU" in s or "2O GRAU" in s:
        return "Médio"
    if "SUPERIOR" in s:
        return "Superior"
    return "Não informado"


def _gender_label(ds: str) -> str:
    s = (ds or "").upper()
    if s.startswith("FEM"):
        return "Feminino"
    if s.startswith("MASC"):
        return "Masculino"
    return "Não informado"


def _ordered(acc: dict[str, int], order: list[str]) -> dict[str, int]:
    """Reordena o dict pelos rótulos canônicos (mantém só os com valor>0)."""
    out = {k: acc[k] for k in order if acc.get(k, 0) > 0}
    # inclui rótulos inesperados ao final
    for k, v in acc.items():
        if k not in out and v > 0:
            out[k] = v
    return out


def _process_perfil_eleitorado(
    db: Session, job: TseSyncJob, zip_path: Path,
) -> None:
    """
    Agrega perfil_eleitorado_2024.csv por município:
    total + gênero + faixa etária (agrupada) + escolaridade (agrupada).
    O CSV tem milhões de linhas (município×zona×gênero×idade×escolaridade×…);
    acumulamos em memória por município (~5.5k chaves) e gravamos 1 linha/muni.
    """
    munis_by_tse: dict[int, UUID] = {
        m.tse_code: m.id for m in db.execute(select(Municipality)).scalars()
    }

    acc: dict[UUID, dict] = {}
    rows_processed = 0

    for _, row in iter_csv_rows(zip_path):
        rows_processed += 1
        code = _i(row.get("CD_MUNICIPIO"))
        muni_id = munis_by_tse.get(code)
        if muni_id is None:
            continue
        qt = _i(row.get("QT_ELEITORES_PERFIL"))
        if qt <= 0:
            continue

        a = acc.get(muni_id)
        if a is None:
            a = acc[muni_id] = {"total": 0, "g": {}, "age": {}, "edu": {}}
        a["total"] += qt
        g = _gender_label(row.get("DS_GENERO", ""))
        a["g"][g] = a["g"].get(g, 0) + qt
        ab = _age_bucket(row.get("DS_FAIXA_ETARIA", ""))
        a["age"][ab] = a["age"].get(ab, 0) + qt
        eb = _edu_bucket(row.get("DS_GRAU_ESCOLARIDADE", ""))
        a["edu"][eb] = a["edu"].get(eb, 0) + qt

        if rows_processed % 200_000 == 0:
            job.rows_processed = rows_processed
            db.commit()
            log.info("tse_perfil_progress", rows=rows_processed, munis=len(acc))

    now = datetime.now(timezone.utc)
    rows_out = [
        {
            "id": uuid4(),
            "municipality_id": mid,
            "year": 2024,
            "total": v["total"],
            "by_gender": _ordered(v["g"], _GENDER_ORDER),
            "by_age": _ordered(v["age"], _AGE_ORDER),
            "by_education": _ordered(v["edu"], _EDU_ORDER),
            "created_at": now,
            "updated_at": now,
        }
        for mid, v in acc.items()
    ]

    # Idempotente: limpa o ano antes de regravar
    db.execute(delete(MunicipalityElectorate).where(MunicipalityElectorate.year == 2024))
    db.commit()

    log.info("tse_perfil_inserting", munis=len(rows_out))
    for i in range(0, len(rows_out), CHUNK_SIZE):
        db.execute(insert(MunicipalityElectorate), rows_out[i : i + CHUNK_SIZE])
        db.commit()
        job.municipalities_imported = len(rows_out[: i + CHUNK_SIZE])
        db.commit()

    job.rows_processed = rows_processed
    db.commit()
    log.info("tse_perfil_done", munis=len(rows_out), rows=rows_processed)


# ====================================================================
# Processor: zona_votos (reprocessa munzona guardando NR_ZONA)
# ====================================================================


def _flush_zone_votes(
    db: Session,
    acc: dict[tuple[UUID, UUID, int], int],
    cand_office: dict[UUID, int],
) -> None:
    """Grava votos por zona via UPSERT-ADD (votes = votes + excluded.votes)."""
    if not acc:
        return
    now = datetime.now(timezone.utc)
    rows = [
        {
            "id": uuid4(),
            "candidate_id": cid,
            "municipality_id": mid,
            "zone": zone,
            "votes": votes,
            "office_code": cand_office.get(cid),
            "created_at": now,
            "updated_at": now,
        }
        for (cid, mid, zone), votes in acc.items()
    ]
    for i in range(0, len(rows), CHUNK_SIZE):
        chunk = rows[i : i + CHUNK_SIZE]
        stmt = pg_insert(CandidateZoneVote.__table__).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=["candidate_id", "municipality_id", "zone"],
            set_={
                "votes": CandidateZoneVote.__table__.c.votes + stmt.excluded.votes,
                "updated_at": now,
            },
        )
        db.execute(stmt)
    db.commit()


def _process_zona_votos(
    db: Session, job: TseSyncJob, zip_path: Path, *, year: int,
) -> None:
    """
    Agrega votos por (candidato, município, zona) do votacao_candidato_munzona.
    Candidatos e municípios já existem (importados antes) — aqui só somamos
    votos nominais por zona. Upsert-add com flush parcial (memória limitada).

    Idempotente: apaga os votos-zona dos candidatos DESTE ano antes de regravar.
    """
    # Carrega só (chave → id), NÃO o objeto ORM inteiro — com 454k candidatos,
    # hidratar objetos completos (c/ colunas JSON) estoura os 768MB do container
    # (OOM kill). Tuplas leves resolvem.
    munis_by_tse: dict[int, UUID] = dict(
        db.execute(select(Municipality.tse_code, Municipality.id)).all()
    )
    candidates_by_sq: dict[int, UUID] = {}
    cand_office: dict[UUID, int] = {}  # candidate_id → cargo (denormalizado)
    for sq, cid, office in db.execute(
        select(Candidate.sq_candidato, Candidate.id, Candidate.office_code)
    ).all():
        candidates_by_sq[sq] = cid
        cand_office[cid] = office

    # Limpa votos-zona dos candidatos deste ano (reimport idempotente)
    cand_ids_year = select(Candidate.id).where(
        Candidate.election_id.in_(select(Election.id).where(Election.year == year))
    )
    db.execute(
        delete(CandidateZoneVote).where(
            CandidateZoneVote.candidate_id.in_(cand_ids_year)
        )
    )
    db.commit()

    acc: dict[tuple[UUID, UUID, int], int] = {}
    rows_processed = 0

    # Só _BRASIL.csv — senão conta votos 2x (zip tem 1 csv por UF idêntico)
    for _, row in iter_csv_rows(zip_path, name_contains="_BRASIL"):
        rows_processed += 1
        # APENAS 1º turno (evita dobrar votos de runoff por zona)
        if (_i(row.get("NR_TURNO")) or 1) != 1:
            continue
        sq = _i(row.get("SQ_CANDIDATO"))
        muni_code = _i(row.get("CD_MUNICIPIO"))
        zone = _i(row.get("NR_ZONA"))
        cid = candidates_by_sq.get(sq)
        mid = munis_by_tse.get(muni_code)
        if cid is None or mid is None or not zone:
            continue
        votes = _i(row.get("QT_VOTOS_NOMINAIS"))
        key = (cid, mid, zone)
        acc[key] = acc.get(key, 0) + votes

        if rows_processed % CHUNK_SIZE == 0:
            job.rows_processed = rows_processed
            db.commit()

        if len(acc) >= VOTE_ACC_MAX:
            _flush_zone_votes(db, acc, cand_office)
            acc.clear()
            log.info("tse_zona_flush", rows=rows_processed)

    _flush_zone_votes(db, acc, cand_office)
    job.rows_processed = rows_processed
    db.commit()
    log.info("tse_zona_done", year=year, rows=rows_processed)
