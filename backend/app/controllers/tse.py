"""
Controller TSE — sync + leitura de dados públicos eleitorais.

Endpoints autenticados (qualquer usuário com JWT vê os mesmos dados —
não há filtro de tenant porque dados TSE são públicos).
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status
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
    ElectionStatsResponse,
    MunicipalityRead,
    MunicipalityResultsResponse,
    PartyRead,
    SyncJobCreated,
    SyncJobRead,
    TopCandidateInMunicipality,
    VoteResultByMunicipality,
)
from app.utils.tse_photos import PhotoNotFound, get_candidate_photo
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
    # Models TSE nao tem relationships ORM definidos (decisao consciente —
    # evita o overhead de carregar tudo). Em vez disso, montamos os nested
    # (party, election) com batch fetch via mapas, mais abaixo.
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


# ============================================================ MUNICIPALITIES


@router.get(
    "/municipalities",
    response_model=Page[MunicipalityRead],
    summary="Listar municipios (paginado, busca por nome/UF)",
)
def list_municipalities(
    ctx: CurrentTenant,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    state: str | None = Query(None, min_length=2, max_length=2),
    search: str | None = Query(None, description="ILIKE no nome do municipio"),
    db: Session = Depends(get_db),
) -> Page[MunicipalityRead]:
    stmt = select(Municipality)
    if state:
        stmt = stmt.where(Municipality.state == state.upper())
    if search:
        stmt = stmt.where(Municipality.name.ilike(f"%{search}%"))

    total = int(
        db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    )

    rows = db.execute(
        stmt.order_by(Municipality.state, Municipality.name).limit(limit).offset(offset)
    ).scalars().all()

    items = [MunicipalityRead.model_validate(m) for m in rows]
    return Page[MunicipalityRead](items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/municipalities/{municipality_id}/top-candidates",
    response_model=MunicipalityResultsResponse,
    summary="Top candidatos num municipio (ordenado por votos desc)",
    description="""\
Retorna os candidatos mais votados em um municipio.
Aceita filtro opcional por `office_code` (11=prefeito, 13=vereador, etc).
""",
)
def municipality_top_candidates(
    municipality_id: UUID,
    ctx: CurrentTenant,
    limit: int = Query(50, ge=1, le=200),
    office_code: int | None = Query(None, description="Filtra por cargo"),
    db: Session = Depends(get_db),
) -> MunicipalityResultsResponse:
    muni = db.get(Municipality, municipality_id)
    if muni is None:
        raise NotFoundError("Municipio nao encontrado")

    stmt = (
        select(VoteResult, Candidate)
        .join(Candidate, VoteResult.candidate_id == Candidate.id)
        .where(VoteResult.municipality_id == municipality_id)
    )
    if office_code is not None:
        stmt = stmt.where(Candidate.office_code == office_code)
    stmt = stmt.order_by(VoteResult.votes.desc()).limit(limit)
    rows = db.execute(stmt).all()

    # Batch fetch party + election pra hidratar nested
    party_ids = {c.party_id for _, c in rows}
    election_ids = {c.election_id for _, c in rows}
    parties_map = {
        p.id: p for p in db.execute(
            select(Party).where(Party.id.in_(party_ids))
        ).scalars()
    } if party_ids else {}
    elections_map = {
        e.id: e for e in db.execute(
            select(Election).where(Election.id.in_(election_ids))
        ).scalars()
    } if election_ids else {}

    results = [
        TopCandidateInMunicipality(
            candidate=CandidateRead(
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
            ),
            votes=vr.votes,
        )
        for vr, c in rows
    ]
    return MunicipalityResultsResponse(
        municipality=MunicipalityRead.model_validate(muni),
        results=results,
        total_results=len(results),
    )


# ============================================================ ELECTIONS DRILL


@router.get(
    "/elections/{election_id}/stats",
    response_model=ElectionStatsResponse,
    summary="Sumario de uma eleicao (n candidatos, n municipios, total votos)",
)
def election_stats(
    election_id: UUID,
    ctx: CurrentTenant,
    db: Session = Depends(get_db),
) -> ElectionStatsResponse:
    election = db.get(Election, election_id)
    if election is None:
        raise NotFoundError("Eleicao nao encontrada")

    candidates_count = int(
        db.execute(
            select(func.count(Candidate.id)).where(Candidate.election_id == election_id)
        ).scalar_one()
    )
    # Sum votos cruzando candidatos da eleicao com vote_results
    candidate_ids_subq = select(Candidate.id).where(Candidate.election_id == election_id)
    total_votes_q = select(func.coalesce(func.sum(VoteResult.votes), 0)).where(
        VoteResult.candidate_id.in_(candidate_ids_subq)
    )
    total_votes = int(db.execute(total_votes_q).scalar_one())
    # Distinct municipios com voto pra eleicao
    munis_q = select(func.count(func.distinct(VoteResult.municipality_id))).where(
        VoteResult.candidate_id.in_(candidate_ids_subq)
    )
    munis_count = int(db.execute(munis_q).scalar_one())

    return ElectionStatsResponse(
        election=ElectionRead.model_validate(election),
        candidates_count=candidates_count,
        municipalities_count=munis_count,
        total_votes=total_votes,
    )


# ============================================================ PHOTO


@router.get(
    "/candidates/{candidate_id}/photo",
    summary="Foto oficial do candidato (TSE)",
    description="""\
Faz proxy da foto oficial publicada pelo TSE em
`cdn.tse.jus.br/.../foto_cand2024_<UF>_div.zip`.

**Tecnica**: extracao por HTTP Range — baixa so ~50KB por foto,
nao o ZIP inteiro de ~2GB. Resultado cacheado em disco
(`/var/marenostrum/tse_photos/{UF}/{sq}.jpg`) — primeira chamada custa
~500ms-1s, repeticoes sao instantaneas.

**Cache HTTP**: `Cache-Control: public, max-age=604800` (7 dias).

Endpoint **publico** (sem JWT) pra permitir `<img src>` direto do navegador
sem precisar enviar bearer token. Foto e dado publico do TSE de qualquer
forma — autenticar so adiciona complicacao sem ganho de seguranca.
""",
    responses={
        200: {
            "content": {"image/jpeg": {}},
            "description": "JPEG da foto",
        },
        404: {"description": "Candidato sem foto cadastrada no TSE"},
    },
    response_class=Response,
    include_in_schema=True,
)
def candidate_photo(
    candidate_id: UUID,
    db: Session = Depends(get_db),
) -> Response:
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise NotFoundError("Candidato nao encontrado")

    try:
        data = get_candidate_photo(candidate.state, candidate.sq_candidato)
    except PhotoNotFound:
        raise NotFoundError("Foto nao disponivel no TSE para este candidato")

    return Response(
        content=data,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=604800",  # 7 dias
            "ETag": f'"tse-{candidate.sq_candidato}"',
        },
    )
