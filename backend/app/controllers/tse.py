"""
Controller TSE — sync + leitura de dados públicos eleitorais.

Endpoints autenticados (qualquer usuário com JWT vê os mesmos dados —
não há filtro de tenant porque dados TSE são públicos).
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import CurrentTenant  # garante autenticado, ignora tenant
from app.core.errors import DomainError, NotFoundError
from app.models.tse import (
    Candidate,
    Election,
    Municipality,
    Party,
    SyncJobStatus,
    TseSyncJob,
    VoteResult,
)
from app.schemas.contact import Page
from app.schemas.tse import (
    CandidateRead,
    CandidateResultsResponse,
    ElectionRead,
    MunicipalityRead,
    PartyRead,
    SyncJobCreated,
    SyncJobRead,
    VoteResultByMunicipality,
)
from app.utils.tse_sync import DATASETS, run_sync_job


class _ConflictError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


router = APIRouter(prefix="/tse", tags=["tse"])


# ============================================================ SYNC


@router.post(
    "/sync",
    response_model=SyncJobCreated,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Disparar sincronização de dataset TSE (background)",
    description="""\
Cria um job de sincronização e dispara em **BackgroundTask** (não bloqueia
o request). Use `GET /tse/sync/{job_id}` pra acompanhar progresso.

### Datasets disponíveis
- `candidato_munzona_2024` — votação por candidato × município (Brasil 2024)

### Estimativa de tempo
~5–10 min na VPS KVM 1 (1 vCPU). Vai baixar ~50MB do TSE + parsear
~600k linhas.

### Idempotência
ZIP é cacheado em `/tmp/tse_cache`. Re-disparar não re-baixa (TSE não
muda dataset histórico). Para forçar refresh, delete o cache + dispare.

### Erros
- **409** se já há job RUNNING desse dataset (evita duplicação)
""",
)
def trigger_sync(
    ctx: CurrentTenant,  # apenas pra exigir autenticação
    background_tasks: BackgroundTasks,
    dataset: str = Query(
        "candidato_munzona_2024",
        description="Identificador do dataset TSE (ver chaves de DATASETS)",
    ),
    db: Session = Depends(get_db),
) -> SyncJobCreated:
    if dataset not in DATASETS:
        raise NotFoundError(
            f"Dataset '{dataset}' não suportado. Disponíveis: {list(DATASETS)}"
        )

    # Verifica se já tem job rodando — evita race
    existing = db.execute(
        select(TseSyncJob).where(
            TseSyncJob.dataset == dataset,
            TseSyncJob.status.in_([SyncJobStatus.PENDING, SyncJobStatus.RUNNING]),
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise _ConflictError(
            f"Já existe sync em andamento pra '{dataset}' (job {existing.id})"
        )

    job = TseSyncJob(
        dataset=dataset,
        year=DATASETS[dataset]["year"],
        status=SyncJobStatus.PENDING,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Dispara background — abre nova sessão DB lá dentro
    background_tasks.add_task(run_sync_job, job.id)

    return SyncJobCreated(job_id=job.id, dataset=dataset, status=job.status)


@router.get(
    "/sync/{job_id}",
    response_model=SyncJobRead,
    summary="Status de um job de sincronização (poll)",
)
def get_sync_job(
    job_id: UUID,
    ctx: CurrentTenant,
    db: Session = Depends(get_db),
) -> SyncJobRead:
    job = db.get(TseSyncJob, job_id)
    if job is None:
        raise NotFoundError("Job não encontrado")
    return SyncJobRead.model_validate(job)


@router.get(
    "/sync",
    response_model=list[SyncJobRead],
    summary="Lista os 20 jobs mais recentes",
)
def list_sync_jobs(
    ctx: CurrentTenant,
    db: Session = Depends(get_db),
) -> list[SyncJobRead]:
    jobs = (
        db.execute(
            select(TseSyncJob).order_by(TseSyncJob.created_at.desc()).limit(20)
        )
        .scalars()
        .all()
    )
    return [SyncJobRead.model_validate(j) for j in jobs]


# ============================================================ READ


@router.get(
    "/elections",
    response_model=list[ElectionRead],
    summary="Listar eleições importadas",
)
def list_elections(
    ctx: CurrentTenant,
    db: Session = Depends(get_db),
) -> list[ElectionRead]:
    items = (
        db.execute(select(Election).order_by(Election.year.desc(), Election.round))
        .scalars()
        .all()
    )
    return [ElectionRead.model_validate(e) for e in items]


@router.get(
    "/parties",
    response_model=list[PartyRead],
    summary="Listar partidos importados",
)
def list_parties(
    ctx: CurrentTenant,
    db: Session = Depends(get_db),
) -> list[PartyRead]:
    items = db.execute(select(Party).order_by(Party.number)).scalars().all()
    return [PartyRead.model_validate(p) for p in items]


@router.get(
    "/candidates",
    response_model=Page[CandidateRead],
    summary="Buscar candidatos (filtros por UF, cargo, partido, nome)",
)
def list_candidates(
    ctx: CurrentTenant,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    state: str | None = Query(None, min_length=2, max_length=2, description="UF: MG, RJ, SP..."),
    office_code: int | None = Query(None, description="11=prefeito, 13=vereador, 1=presidente"),
    party_number: int | None = Query(None, description="Número do partido (ex: 13 = PT)"),
    search: str | None = Query(None, description="Busca ILIKE no nome/urna"),
    election_id: UUID | None = Query(None),
    db: Session = Depends(get_db),
) -> Page[CandidateRead]:
    # Query base com joinedload pra montar nested (party, election) sem N+1
    stmt = select(Candidate).options(
        joinedload(Candidate.party) if False else joinedload  # placeholder
    )
    # Nota: como models nao tem relationships definidos, vou fazer manualmente:
    stmt = select(Candidate)
    if state:
        stmt = stmt.where(Candidate.state == state.upper())
    if office_code is not None:
        stmt = stmt.where(Candidate.office_code == office_code)
    if election_id is not None:
        stmt = stmt.where(Candidate.election_id == election_id)
    if search:
        stmt = stmt.where(
            (Candidate.name.ilike(f"%{search}%"))
            | (Candidate.urn_name.ilike(f"%{search}%"))
        )

    if party_number is not None:
        party_id_subq = select(Party.id).where(Party.number == party_number)
        stmt = stmt.where(Candidate.party_id.in_(party_id_subq))

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = int(db.execute(count_stmt).scalar_one())

    # Paginação
    rows = db.execute(
        stmt.order_by(Candidate.urn_name).limit(limit).offset(offset)
    ).scalars().all()

    # Hidrata party + election em batch (evita N+1)
    party_ids = {c.party_id for c in rows}
    election_ids = {c.election_id for c in rows}
    parties_map = {
        p.id: p for p in db.execute(
            select(Party).where(Party.id.in_(party_ids))
        ).scalars()
    }
    elections_map = {
        e.id: e for e in db.execute(
            select(Election).where(Election.id.in_(election_ids))
        ).scalars()
    }

    items = []
    for c in rows:
        items.append(CandidateRead(
            id=c.id,
            number=c.number,
            name=c.name,
            urn_name=c.urn_name,
            office_code=c.office_code,
            office_name=c.office_name,
            state=c.state,
            situation=c.situation,
            party=PartyRead.model_validate(parties_map[c.party_id]),
            election=ElectionRead.model_validate(elections_map[c.election_id]),
        ))

    return Page[CandidateRead](items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/candidates/{candidate_id}/results",
    response_model=CandidateResultsResponse,
    summary="Votos do candidato por município (ordenado por votos desc)",
)
def candidate_results(
    candidate_id: UUID,
    ctx: CurrentTenant,
    db: Session = Depends(get_db),
) -> CandidateResultsResponse:
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise NotFoundError("Candidato não encontrado")

    party = db.get(Party, candidate.party_id)
    election = db.get(Election, candidate.election_id)

    # Join VoteResult × Municipality, ordenado por votos desc
    stmt = (
        select(VoteResult, Municipality)
        .join(Municipality, VoteResult.municipality_id == Municipality.id)
        .where(VoteResult.candidate_id == candidate_id)
        .order_by(VoteResult.votes.desc())
    )
    rows = db.execute(stmt).all()

    results = [
        VoteResultByMunicipality(
            municipality=MunicipalityRead.model_validate(m),
            votes=vr.votes,
        )
        for vr, m in rows
    ]
    total = sum(r.votes for r in results)

    return CandidateResultsResponse(
        candidate=CandidateRead(
            id=candidate.id,
            number=candidate.number,
            name=candidate.name,
            urn_name=candidate.urn_name,
            office_code=candidate.office_code,
            office_name=candidate.office_name,
            state=candidate.state,
            situation=candidate.situation,
            party=PartyRead.model_validate(party),
            election=ElectionRead.model_validate(election),
        ),
        results=results,
        total_votes=total,
        municipalities_with_votes=len(results),
    )
