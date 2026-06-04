"""
Controller TSE — sync + leitura de dados públicos eleitorais.

Endpoints autenticados (qualquer usuário com JWT vê os mesmos dados —
não há filtro de tenant porque dados TSE são públicos).
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request, Response, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, joinedload

from app.utils.agg_cache import agg_get, agg_set

from app.core.database import get_db
from app.core.dependencies import CurrentTenant  # garante autenticado, ignora tenant
from app.core.errors import DomainError, NotFoundError
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
from app.schemas.contact import Page
from app.schemas.tse import (
    CandidateByNeighborhoodItem,
    CandidateByNeighborhoodResponse,
    CandidateRead,
    CandidateResultsResponse,
    CandidateTrajectoryResponse,
    CandidateZoneVotesResponse,
    ElectionRead,
    ElectionStatsResponse,
    ElectorateResponse,
    ZoneTopCandidate,
    ZoneVoteItem,
    MunicipalityRead,
    MunicipalityResultsResponse,
    MunicipalityTimelineResponse,
    MunicipalityZone,
    MunicipalityZonesResponse,
    OpportunityMunicipality,
    OpportunityResponse,
    TimelineItem,
    TimelineWinner,
    TrajectoryItem,
    PartyEvolutionItem,
    PartyEvolutionResponse,
    PartyPerformanceItem,
    PartyPerformanceResponse,
    PartyRead,
    RankedCandidate,
    SyncJobCreated,
    SyncJobRead,
    TopCandidateInMunicipality,
    TopCandidatesResponse,
    VoteResultByMunicipality,
    WinnerMapPoint,
    WinnersMapResponse,
)
from app.utils.rate_limit import limiter
from app.utils.tse_pdf import build_candidate_dossier
from app.utils.tse_photos import PhotoNotFound, get_candidate_photo, get_or_make_webp
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
@limiter.limit("3/hour")
def trigger_sync(
    request: Request,
    ctx: CurrentTenant,  # apenas pra exigir autenticação
    background_tasks: BackgroundTasks,
    dataset: str = Query(
        "candidato_munzona_2024",
        description="Identificador do dataset TSE (ver chaves de DATASETS)",
    ),
    db: Session = Depends(get_db),
) -> SyncJobCreated:
    # 3/hora por IP — sync e caro (~10min, baixa 50MB do TSE, parsea 600k+
    # linhas). Ninguem precisa disparar isso varias vezes por hora.
    if dataset not in DATASETS:
        raise NotFoundError(
            f"Dataset '{dataset}' não suportado. Disponíveis: {list(DATASETS)}"
        )

    # Auto-cleanup de jobs orfaos: se ja tem job "running" ha mais de 1h
    # sem updated_at recente, marca como failed (provavelmente container
    # caiu durante a sync). Sem isso, jobs ficam "presos" e bloqueiam novos.
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    orphans = db.execute(
        select(TseSyncJob).where(
            TseSyncJob.dataset == dataset,
            TseSyncJob.status.in_([SyncJobStatus.PENDING, SyncJobStatus.RUNNING]),
            TseSyncJob.updated_at < cutoff,
        )
    ).scalars().all()
    for o in orphans:
        o.status = SyncJobStatus.FAILED
        o.error_message = "Orphan: stuck running with no progress for >1h"
        o.completed_at = datetime.now(timezone.utc)
    if orphans:
        db.commit()

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
    # Cleanup oportunista de jobs orfaos (status "running" sem progresso ha >1h).
    # Acontece quando o container reinicia durante uma sync. Sem isso, o badge
    # "sincronizando..." fica preso na UI ate proximo POST /sync.
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    orphans = db.execute(
        select(TseSyncJob).where(
            TseSyncJob.status.in_([SyncJobStatus.PENDING, SyncJobStatus.RUNNING]),
            TseSyncJob.updated_at < cutoff,
        )
    ).scalars().all()
    if orphans:
        now = datetime.now(timezone.utc)
        for o in orphans:
            o.status = SyncJobStatus.FAILED
            o.error_message = "Orphan: stuck >1h sem progresso (container reiniciou)"
            o.completed_at = now
        db.commit()

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
    "/parties/{number}/evolution",
    response_model=PartyEvolutionResponse,
    summary="Evolução do partido por eleição (eleitos/candidatos/votos por ano)",
    description=(
        "Soma todos os cargos por ano. Permite ver crescimento/declínio do "
        "partido ao longo das eleições disponíveis (2014–2024)."
    ),
)
def party_evolution(
    number: int,
    ctx: CurrentTenant,
    db: Session = Depends(get_db),
) -> PartyEvolutionResponse:
    party = db.execute(
        select(Party).where(Party.number == number)
    ).scalars().first()
    if party is None:
        raise NotFoundError("Partido não encontrado")

    # Todos os party_ids com essa sigla/numero (migrações históricas podem ter
    # gerado >1 registro pro mesmo número). Agrega todos.
    party_ids = [
        p.id for p in db.execute(
            select(Party).where(Party.number == number)
        ).scalars()
    ]

    rows = db.execute(
        select(
            Election.year,
            func.count(Candidate.id).label("cands"),
            func.count(Candidate.id)
            .filter(Candidate.result_status.like("ELEITO%"))
            .label("eleitos"),
            func.coalesce(func.sum(Candidate.total_votes), 0).label("votos"),
        )
        .join(Election, Candidate.election_id == Election.id)
        .where(Candidate.party_id.in_(party_ids))
        .group_by(Election.year)
        .order_by(Election.year.asc())
    ).all()

    items = [
        PartyEvolutionItem(
            year=int(r.year),
            elected_count=int(r.eleitos),
            candidates_count=int(r.cands),
            total_votes=int(r.votos),
        )
        for r in rows
    ]
    return PartyEvolutionResponse(
        party=PartyRead.model_validate(party),
        items=items,
    )


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
    year: int | None = Query(None, description="Ano da eleição (2024, 2022...)"),
    elected_only: bool = Query(False, description="Filtra so candidatos eleitos"),
    municipality_id: UUID | None = Query(None, description="Filtra so candidatos que tiveram votos nesta cidade"),
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
    if year is not None:
        stmt = stmt.where(
            Candidate.election_id.in_(
                select(Election.id).where(Election.year == year)
            )
        )
    if search:
        # Busca acento-insensivel por PALAVRA, hibrida:
        #
        # 1. ILIKE '%termo%' — RAPIDO porque bate o indice GIN trgm
        #    (ix_tse_candidates_{name,urn}_unaccent_trgm). Narrows 962k -> ~poucos
        #    milhares em ~ms.
        # 2. ~* '\mtermo' (regex word boundary) — PRECISO, elimina falsos
        #    positivos como "celular"/"hollulanca". Roda APENAS no subset
        #    ja' filtrado pelo trigram (fast).
        #
        # Sem (1) regex sozinha varre tabela inteira -> 504 timeout.
        # Sem (2) ILIKE sozinha = falsos positivos "celular" pra busca "lula".
        raw = search.strip().lower()
        import re as _re
        esc = _re.escape(raw)
        pattern = f"\\m{esc}"
        ilike_pat = f"%{raw}%"
        stmt = stmt.where(
            # Filtro trigram (usa indice)
            (
                func.f_unaccent(Candidate.name).ilike(func.f_unaccent(ilike_pat))
                | func.f_unaccent(Candidate.urn_name).ilike(func.f_unaccent(ilike_pat))
            )
            # Filtro word-boundary (preciso)
            & (
                func.f_unaccent(Candidate.name).op("~*")(func.f_unaccent(pattern))
                | func.f_unaccent(Candidate.urn_name).op("~*")(func.f_unaccent(pattern))
            )
        )

    if party_number is not None:
        party_id_subq = select(Party.id).where(Party.number == party_number)
        stmt = stmt.where(Candidate.party_id.in_(party_id_subq))

    if elected_only:
        stmt = stmt.where(Candidate.result_status.like("ELEITO%"))

    if municipality_id is not None:
        # So inclui candidatos que tiveram votos nesta cidade.
        # Subquery DISTINCT pra evitar dup quando candidato tem N vote_results.
        cand_ids_in_muni = (
            select(VoteResult.candidate_id)
            .where(VoteResult.municipality_id == municipality_id)
            .distinct()
        )
        stmt = stmt.where(Candidate.id.in_(cand_ids_in_muni))

    # Count total com CAP: contar exato todos os "silva" (77k) e' lento e
    # inutil pra UI. Limitamos a contagem em COUNT_CAP+1 — se passar, a UI
    # mostra "5000+". A subquery com LIMIT faz o Postgres parar cedo.
    COUNT_CAP = 5000
    capped_subq = stmt.with_only_columns(Candidate.id).limit(COUNT_CAP + 1).subquery()
    total = int(db.execute(select(func.count()).select_from(capped_subq)).scalar_one())

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
            result_status=c.result_status,
            party=PartyRead.model_validate(parties_map[c.party_id]),
            election=ElectionRead.model_validate(elections_map[c.election_id]),
        ))

    return Page[CandidateRead](items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/candidates/{candidate_id}/opportunities",
    response_model=OpportunityResponse,
    summary="Radar de oportunidades: eleitorado x votos (redutos vs crescer)",
    description=(
        "Cruza os votos do candidato por município com o eleitorado registrado "
        "(IBGE/TSE). Identifica REDUTOS (maior penetração — consolidar) e "
        "OPORTUNIDADES (maior eleitorado com baixa penetração — onde crescer). "
        "É o 'onde buscar voto' que transforma histórico em estratégia."
    ),
)
def candidate_opportunities(
    candidate_id: UUID,
    ctx: CurrentTenant,
    db: Session = Depends(get_db),
) -> OpportunityResponse:
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise NotFoundError("Candidato não encontrado")

    # Eleitorado mais recente por município (pode haver >1 ano na tabela).
    latest_elect = (
        select(
            MunicipalityElectorate.municipality_id.label("mid"),
            func.max(MunicipalityElectorate.year).label("y"),
        )
        .group_by(MunicipalityElectorate.municipality_id)
        .subquery()
    )

    # Votos do candidato × eleitorado, por município.
    rows = db.execute(
        select(
            Municipality.id,
            Municipality.name,
            Municipality.state,
            VoteResult.votes,
            MunicipalityElectorate.total,
        )
        .join(VoteResult, VoteResult.municipality_id == Municipality.id)
        .join(
            latest_elect,
            latest_elect.c.mid == Municipality.id,
        )
        .join(
            MunicipalityElectorate,
            (MunicipalityElectorate.municipality_id == Municipality.id)
            & (MunicipalityElectorate.year == latest_elect.c.y),
        )
        .where(VoteResult.candidate_id == candidate_id)
    ).all()

    items: list[OpportunityMunicipality] = []
    total_votes = 0
    total_elect = 0
    for mid, name, state, votes, elect in rows:
        votes = int(votes or 0)
        elect = int(elect or 0)
        total_votes += votes
        total_elect += elect
        pen = (votes / elect * 100) if elect > 0 else 0.0
        items.append(
            OpportunityMunicipality(
                municipality_id=mid,
                name=name,
                state=state,
                electorate=elect,
                votes=votes,
                penetration_pct=round(pen, 2),
                available=max(0, elect - votes),
                category="neutro",
            )
        )

    avg_pen = (total_votes / total_elect * 100) if total_elect > 0 else 0.0

    # Redutos: maior penetração (consolidar a base). Mín. de relevância: 500
    # eleitores pra não pegar cidade minúscula com 1 voto = 50%.
    relevant = [i for i in items if i.electorate >= 500]
    strongholds = sorted(relevant, key=lambda i: i.penetration_pct, reverse=True)[:10]
    for s in strongholds:
        s.category = "reduto"

    # Oportunidades: maior eleitorado disponível (eleitorado grande × baixa
    # penetração). Score = available × (1 - penetração normalizada). Ordena por
    # eleitores "a conquistar" mas penaliza onde já domina.
    sids = {s.municipality_id for s in strongholds}
    opp_pool = [i for i in relevant if i.municipality_id not in sids]
    opportunities = sorted(
        opp_pool,
        key=lambda i: i.available * (1 - min(i.penetration_pct, 50) / 100),
        reverse=True,
    )[:10]
    for o in opportunities:
        o.category = "crescer"

    return OpportunityResponse(
        candidate_id=candidate.id,
        total_electorate_reached=total_elect,
        total_votes=total_votes,
        avg_penetration_pct=round(avg_pen, 2),
        strongholds=strongholds,
        opportunities=opportunities,
    )


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
            result_status=candidate.result_status,
            assets_total=candidate.assets_total,
            social_links=candidate.social_links,
            revenue_total=candidate.revenue_total,
            expense_total=candidate.expense_total,
            party=PartyRead.model_validate(party),
            election=ElectionRead.model_validate(election),
        ),
        results=results,
        total_votes=total,
        municipalities_with_votes=len(results),
    )


@router.get(
    "/candidates/{candidate_id}/trajectory",
    response_model=CandidateTrajectoryResponse,
    summary="Trajetória eleitoral da pessoa (mesma pessoa em várias eleições)",
    description=(
        "Encontra todas as candidaturas da MESMA pessoa (match por nome civil "
        "completo, case/acento-insensível) ao longo das eleições disponíveis "
        "(2014–2024), ordenadas do mais recente pro mais antigo. Permite ver a "
        "evolução de cargo, partido e votos de um político ao longo de 10 anos."
    ),
)
def candidate_trajectory(
    candidate_id: UUID,
    ctx: CurrentTenant,
    db: Session = Depends(get_db),
) -> CandidateTrajectoryResponse:
    base = db.get(Candidate, candidate_id)
    if base is None:
        raise NotFoundError("Candidato não encontrado")

    # Match por nome civil completo (NM_CANDIDATO) normalizado — estável entre
    # eleições (nome de urna muda mais). f_unaccent + lower pra robustez.
    # Index ix_tse_candidates_name_unaccent_trgm acelera o filtro.
    norm = func.lower(func.f_unaccent(base.name))
    stmt = (
        select(Candidate, Election, Party)
        .join(Election, Candidate.election_id == Election.id)
        .join(Party, Candidate.party_id == Party.id)
        .where(func.lower(func.f_unaccent(Candidate.name)) == norm)
        .order_by(Election.year.desc(), Candidate.office_code.asc())
    )
    rows = db.execute(stmt).all()

    items = [
        TrajectoryItem(
            candidate_id=c.id,
            year=e.year,
            office_code=c.office_code,
            office_name=c.office_name,
            state=c.state,
            party_abbreviation=p.abbreviation,
            party_number=p.number,
            number=c.number,
            total_votes=c.total_votes,
            result_status=c.result_status,
        )
        for c, e, p in rows
    ]

    return CandidateTrajectoryResponse(
        name=base.name,
        current_id=base.id,
        items=items,
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
    # Exclui "ZZ" (Exterior) — zonas de votação no exterior p/ presidente,
    # não são municípios reais. Sem isso a contagem fica 5.752 em vez de ~5.571.
    stmt = select(Municipality).where(Municipality.state != "ZZ")
    if state:
        stmt = stmt.where(Municipality.state == state.upper())
    if search:
        stmt = stmt.where(
            func.f_unaccent(Municipality.name).ilike(func.f_unaccent(f"%{search}%"))
        )

    total = int(
        db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    )

    rows = db.execute(
        stmt.order_by(Municipality.state, Municipality.name).limit(limit).offset(offset)
    ).scalars().all()

    items = [MunicipalityRead.model_validate(m) for m in rows]
    return Page[MunicipalityRead](items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/municipalities/{municipality_id}",
    response_model=MunicipalityRead,
    summary="Pega um município pelo ID (p/ hidratar URL compartilhável)",
)
def get_municipality(
    municipality_id: UUID,
    ctx: CurrentTenant,
    db: Session = Depends(get_db),
) -> MunicipalityRead:
    m = db.get(Municipality, municipality_id)
    if m is None:
        raise NotFoundError("Município não encontrado")
    return MunicipalityRead.model_validate(m)


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
    limit: int = Query(50, ge=1, le=500),
    office_code: int | None = Query(None, description="Filtra por cargo"),
    year: int | None = Query(None, description="Ano da eleição (2024, 2022...)"),
    db: Session = Depends(get_db),
) -> MunicipalityResultsResponse:
    muni = db.get(Municipality, municipality_id)
    if muni is None:
        raise NotFoundError("Municipio nao encontrado")

    election_ids_subq = (
        select(Election.id).where(Election.year == year) if year is not None else None
    )

    stmt = (
        select(VoteResult, Candidate)
        .join(Candidate, VoteResult.candidate_id == Candidate.id)
        .where(VoteResult.municipality_id == municipality_id)
    )
    if office_code is not None:
        stmt = stmt.where(Candidate.office_code == office_code)
    if election_ids_subq is not None:
        stmt = stmt.where(Candidate.election_id.in_(election_ids_subq))
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
                result_status=c.result_status,
                party=PartyRead.model_validate(parties_map[c.party_id]),
                election=ElectionRead.model_validate(elections_map[c.election_id]),
            ),
            votes=vr.votes,
        )
        for vr, c in rows
    ]

    # Total de votos do cargo no municipio (denominador pra %) — soma TODOS
    # os candidatos, nao so os top N retornados.
    total_stmt = (
        select(func.coalesce(func.sum(VoteResult.votes), 0))
        .join(Candidate, VoteResult.candidate_id == Candidate.id)
        .where(VoteResult.municipality_id == municipality_id)
    )
    if office_code is not None:
        total_stmt = total_stmt.where(Candidate.office_code == office_code)
    if election_ids_subq is not None:
        total_stmt = total_stmt.where(Candidate.election_id.in_(election_ids_subq))
    total_votes = int(db.execute(total_stmt).scalar_one())

    office_name = results[0].candidate.office_name if results else None

    return MunicipalityResultsResponse(
        municipality=MunicipalityRead.model_validate(muni),
        results=results,
        total_results=len(results),
        total_votes=total_votes,
        office_code=office_code,
        office_name=office_name,
    )


@router.get(
    "/municipalities/{municipality_id}/electorate",
    response_model=ElectorateResponse,
    summary="Perfil do eleitorado do município (gênero/idade/escolaridade)",
)
def municipality_electorate(
    municipality_id: UUID,
    ctx: CurrentTenant,
    year: int = Query(2024),
    db: Session = Depends(get_db),
) -> ElectorateResponse:
    muni = db.get(Municipality, municipality_id)
    if muni is None:
        raise NotFoundError("Município não encontrado")
    prof = db.execute(
        select(MunicipalityElectorate).where(
            MunicipalityElectorate.municipality_id == municipality_id,
            MunicipalityElectorate.year == year,
        )
    ).scalar_one_or_none()
    if prof is None:
        raise NotFoundError(
            "Perfil do eleitorado não disponível (sincronize 'perfil_eleitorado_2024')."
        )
    return ElectorateResponse(
        municipality=MunicipalityRead.model_validate(muni),
        year=prof.year,
        total=prof.total,
        by_gender=prof.by_gender or {},
        by_age=prof.by_age or {},
        by_education=prof.by_education or {},
    )


@router.get(
    "/municipalities/{municipality_id}/timeline",
    response_model=MunicipalityTimelineResponse,
    summary="Linha do tempo eleitoral do municipio — vencedor por ano/cargo",
    description="""\
Pra cada (ano, cargo) com dados sincronizados, retorna o vencedor + vice
+ contagem total na cidade. Permite analise comparativa:
- "Quem ganhou prefeito 2024 vs governador 2022?"
- "Onde a esquerda perdeu prefeitura mas Lula ganhou?"
- "Transicao partidaria do municipio"
""",
)
def municipality_timeline(
    municipality_id: UUID,
    ctx: CurrentTenant,
    db: Session = Depends(get_db),
) -> MunicipalityTimelineResponse:
    _key = f"muni_timeline:{municipality_id}"
    _hit = agg_get(_key)
    if _hit is not None:
        return _hit

    muni = db.get(Municipality, municipality_id)
    if muni is None:
        raise NotFoundError("Municipio nao encontrado")

    # Window function: ranqueia candidatos por (election_id, office_code)
    # filtrando por esta cidade. Pega top 2 (vencedor + vice).
    from sqlalchemy import literal_column
    ranked = (
        select(
            VoteResult.candidate_id.label("cand_id"),
            VoteResult.votes.label("votes"),
            Candidate.election_id.label("election_id"),
            Candidate.office_code.label("office_code"),
            func.row_number().over(
                partition_by=(Candidate.election_id, Candidate.office_code),
                order_by=VoteResult.votes.desc(),
            ).label("rn"),
        )
        .join(Candidate, Candidate.id == VoteResult.candidate_id)
        .where(VoteResult.municipality_id == municipality_id)
        .subquery()
    )
    top2 = (
        select(
            ranked.c.cand_id,
            ranked.c.votes,
            ranked.c.election_id,
            ranked.c.office_code,
            ranked.c.rn,
        )
        .where(ranked.c.rn <= 2)
    )
    rows = db.execute(top2).all()

    # Mapa (election_id, office_code) -> {"rn1": (cand_id, votes), "rn2": ...}
    buckets: dict[tuple, dict] = {}
    for r in rows:
        key = (r.election_id, r.office_code)
        slot = buckets.setdefault(key, {})
        slot[r.rn] = (r.cand_id, int(r.votes))

    if not buckets:
        return MunicipalityTimelineResponse(
            municipality=MunicipalityRead.model_validate(muni),
            items=[],
        )

    # Batch-load candidates, parties, elections referenciados
    cand_ids: set = set()
    for slot in buckets.values():
        for v in slot.values():
            cand_ids.add(v[0])
    cands = {
        c.id: c for c in db.execute(
            select(Candidate).where(Candidate.id.in_(cand_ids))
        ).scalars()
    }
    party_ids = {c.party_id for c in cands.values()}
    parties = {
        p.id: p for p in db.execute(
            select(Party).where(Party.id.in_(party_ids))
        ).scalars()
    }
    election_ids = {key[0] for key in buckets.keys()}
    elections = {
        e.id: e for e in db.execute(
            select(Election).where(Election.id.in_(election_ids))
        ).scalars()
    }

    # Total de votos por (election, office) — denominador
    total_rows = db.execute(
        select(
            Candidate.election_id,
            Candidate.office_code,
            func.coalesce(func.sum(VoteResult.votes), 0).label("total"),
            func.count(VoteResult.candidate_id).label("cands"),
        )
        .join(Candidate, Candidate.id == VoteResult.candidate_id)
        .where(VoteResult.municipality_id == municipality_id)
        .group_by(Candidate.election_id, Candidate.office_code)
    ).all()
    totals = {
        (r.election_id, r.office_code): (int(r.total), int(r.cands))
        for r in total_rows
    }

    def _winner(cand_id, votes) -> TimelineWinner:
        c = cands[cand_id]
        p = parties.get(c.party_id)
        return TimelineWinner(
            candidate_id=c.id,
            urn_name=c.urn_name,
            name=c.name,
            party_abbr=p.abbreviation if p else "",
            party_number=p.number if p else 0,
            party_name=p.name if p else "",
            result_status=c.result_status,
            votes=votes,
        )

    items: list[TimelineItem] = []
    for (election_id, office_code), slot in buckets.items():
        e = elections.get(election_id)
        if e is None:
            continue
        winner_data = slot.get(1)
        runner_data = slot.get(2)
        winner_cand = cands.get(winner_data[0]) if winner_data else None
        office_name = winner_cand.office_name if winner_cand else f"Cargo {office_code}"
        total, ncands = totals.get((election_id, office_code), (0, 0))
        items.append(TimelineItem(
            year=e.year,
            office_code=office_code,
            office_name=office_name,
            round=getattr(e, "round", 1) or 1,
            total_votes=total,
            winner=_winner(*winner_data) if winner_data else None,
            runner_up=_winner(*runner_data) if runner_data else None,
            candidates_count=ncands,
        ))

    # Ordena: ano desc, office_code asc (Presidente, Governador, ...),
    # round desc (mostra 2o turno antes do 1o pra cargos que tiveram turno).
    items.sort(key=lambda x: (-x.year, x.office_code, -x.round))

    result = MunicipalityTimelineResponse(
        municipality=MunicipalityRead.model_validate(muni),
        items=items,
    )
    agg_set(_key, result)
    return result


@router.get(
    "/municipalities/{municipality_id}/zones",
    response_model=MunicipalityZonesResponse,
    summary="Top candidatos por zona eleitoral num município (cargo/ano)",
)
def municipality_zones(
    municipality_id: UUID,
    ctx: CurrentTenant,
    office_code: int = Query(11, description="11=prefeito, 13=vereador"),
    year: int = Query(2024),
    top_per_zone: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
) -> MunicipalityZonesResponse:
    _key = f"muni_zones:{municipality_id}:{office_code}:{year}:{top_per_zone}"
    _hit = agg_get(_key)
    if _hit is not None:
        return _hit
    muni = db.get(Municipality, municipality_id)
    if muni is None:
        raise NotFoundError("Município não encontrado")

    # Filtro base (índice municipality_id, office_code, votes)
    base_filter = (
        CandidateZoneVote.municipality_id == municipality_id,
        CandidateZoneVote.office_code == office_code,
    )

    # Total de votos por zona (soma de TODOS) — agregação leve sobre o índice.
    totals = dict(
        db.execute(
            select(CandidateZoneVote.zone, func.sum(CandidateZoneVote.votes))
            .where(*base_filter)
            .group_by(CandidateZoneVote.zone)
        ).all()
    )

    # Top N por zona via window function — só ~N×zonas linhas voltam (em vez de
    # dezenas de milhares em cidades grandes), e o JOIN com candidato é só nelas.
    rn = func.row_number().over(
        partition_by=CandidateZoneVote.zone,
        order_by=CandidateZoneVote.votes.desc(),
    ).label("rn")
    ranked = (
        select(
            CandidateZoneVote.candidate_id.label("cid"),
            CandidateZoneVote.zone.label("zone"),
            CandidateZoneVote.votes.label("votes"),
            rn,
        )
        .where(*base_filter)
        .subquery()
    )
    rows = db.execute(
        select(ranked.c.zone, ranked.c.votes, Candidate)
        .join(Candidate, Candidate.id == ranked.c.cid)
        .where(ranked.c.rn <= top_per_zone)
        .order_by(ranked.c.zone, ranked.c.votes.desc())
    ).all()

    # Agrupa por zona (top N já vem ordenado)
    parties_cache: dict[UUID, Party] = {}
    elections_cache: dict[UUID, Election] = {}
    zones_map: dict[int, dict] = {}
    for zone, votes, cand in rows:
        z = zones_map.setdefault(zone, {"total": int(totals.get(zone, 0)), "cands": []})
        if cand.party_id not in parties_cache:
            parties_cache[cand.party_id] = db.get(Party, cand.party_id)
        if cand.election_id not in elections_cache:
            elections_cache[cand.election_id] = db.get(Election, cand.election_id)
        z["cands"].append((cand, int(votes)))

    office_name = rows[0][2].office_name if rows else None
    zones = [
        MunicipalityZone(
            zone=zone,
            total_votes=info["total"],
            candidates=[
                ZoneTopCandidate(
                    candidate=CandidateRead(
                        id=c.id, number=c.number, name=c.name, urn_name=c.urn_name,
                        office_code=c.office_code, office_name=c.office_name,
                        state=c.state, situation=c.situation,
                        result_status=c.result_status,
                        party=PartyRead.model_validate(parties_cache[c.party_id]),
                        election=ElectionRead.model_validate(elections_cache[c.election_id]),
                    ),
                    votes=v,
                )
                for c, v in info["cands"]
            ],
        )
        for zone, info in sorted(zones_map.items())
    ]
    _result = MunicipalityZonesResponse(
        municipality=MunicipalityRead.model_validate(muni),
        office_code=office_code,
        office_name=office_name,
        zones=zones,
    )
    agg_set(_key, _result)
    return _result


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


# ============================================================ PARTY PERFORMANCE


@router.get(
    "/stats/party-performance",
    response_model=PartyPerformanceResponse,
    summary="Desempenho dos partidos: votos + eleitos por partido",
    description="""\
Ranking de partidos por votos e número de eleitos, numa eleição (ano).
Filtros opcionais: `office_code` (cargo) e `state` (UF).
Base para gráficos (eleitos por partido) e página de Partido.
""",
)
def party_performance(
    ctx: CurrentTenant,
    year: int = Query(2024, description="Ano da eleição"),
    office_code: int | None = Query(None),
    state: str | None = Query(None, min_length=2, max_length=2),
    db: Session = Depends(get_db),
) -> PartyPerformanceResponse:
    _key = f"party_perf:{year}:{office_code}:{(state or '').upper()}"
    _hit = agg_get(_key)
    if _hit is not None:
        return _hit

    # Filtro base sobre candidatos (ano + cargo + UF)
    election_ids = select(Election.id).where(Election.year == year)

    cand_filters = [Candidate.election_id.in_(election_ids)]
    if office_code is not None:
        cand_filters.append(Candidate.office_code == office_code)
    if state is not None:
        cand_filters.append(Candidate.state == state.upper())

    # 1) Votos por partido (soma vote_results dos candidatos filtrados)
    votes_rows = db.execute(
        select(
            Candidate.party_id,
            func.coalesce(func.sum(VoteResult.votes), 0),
        )
        .join(VoteResult, VoteResult.candidate_id == Candidate.id)
        .where(*cand_filters)
        .group_by(Candidate.party_id)
    ).all()
    votes_by_party = {pid: int(v) for pid, v in votes_rows}

    # 2) Contagem de candidatos + eleitos por partido
    counts_rows = db.execute(
        select(
            Candidate.party_id,
            func.count(Candidate.id),
            func.count(Candidate.id).filter(
                Candidate.result_status.like("ELEITO%")
            ),
        )
        .where(*cand_filters)
        .group_by(Candidate.party_id)
    ).all()

    party_ids = [pid for pid, _, _ in counts_rows]
    parties_map = {
        p.id: p
        for p in db.execute(select(Party).where(Party.id.in_(party_ids))).scalars()
    }

    items = []
    for pid, n_cand, n_elected in counts_rows:
        p = parties_map.get(pid)
        if p is None:
            continue
        items.append(
            PartyPerformanceItem(
                party=PartyRead.model_validate(p),
                total_votes=votes_by_party.get(pid, 0),
                elected_count=int(n_elected or 0),
                candidates_count=int(n_cand),
            )
        )
    # Ordena por eleitos desc, depois votos desc
    items.sort(key=lambda i: (i.elected_count, i.total_votes), reverse=True)

    office_name = None
    if office_code is not None:
        row = db.execute(
            select(Candidate.office_name).where(*cand_filters).limit(1)
        ).first()
        office_name = row[0] if row else None

    _result = PartyPerformanceResponse(
        year=year,
        office_code=office_code,
        office_name=office_name,
        state=state.upper() if state else None,
        items=items,
        total_votes=sum(i.total_votes for i in items),
        total_elected=sum(i.elected_count for i in items),
    )
    agg_set(_key, _result)
    return _result


# ============================================================ MAPA VENCEDORES


@router.get(
    "/stats/winners-map",
    response_model=WinnersMapResponse,
    summary="Partido vencedor por município (mapa colorido)",
    description="""\
Para cada município, retorna o candidato/partido mais votado no cargo+ano.
Ex: prefeito 2024 (mapa partidário do Brasil) ou presidente 2022.
Usa DISTINCT ON pra pegar o top por município. Só municípios com coords.
""",
)
def winners_map(
    ctx: CurrentTenant,
    year: int = Query(2024),
    office_code: int = Query(11, description="11=prefeito, 1=presidente, 3=governador"),
    db: Session = Depends(get_db),
) -> WinnersMapResponse:
    _key = f"winners_map:{year}:{office_code}"
    _hit = agg_get(_key)
    if _hit is not None:
        return _hit

    # DISTINCT ON (municipio) ordenado por votos desc → vencedor por municipio.
    sql = text(
        """
        SELECT DISTINCT ON (vr.municipality_id)
          m.id AS municipality_id, m.name, m.state, m.latitude, m.longitude,
          p.number AS party_number, p.abbreviation AS party_abbreviation,
          c.urn_name AS winner_name, vr.votes
        FROM tse_vote_results vr
        JOIN tse_candidates c ON c.id = vr.candidate_id
        JOIN tse_elections e ON e.id = c.election_id
        JOIN tse_parties p ON p.id = c.party_id
        JOIN tse_municipalities m ON m.id = vr.municipality_id
        WHERE e.year = :year AND c.office_code = :office
          AND m.latitude IS NOT NULL
        ORDER BY vr.municipality_id, vr.votes DESC
        """
    )
    rows = db.execute(sql, {"year": year, "office": office_code}).mappings().all()
    points = [
        WinnerMapPoint(
            municipality_id=r["municipality_id"],
            name=r["name"],
            state=r["state"],
            lat=float(r["latitude"]),
            lng=float(r["longitude"]),
            party_number=int(r["party_number"]),
            party_abbreviation=r["party_abbreviation"],
            winner_name=r["winner_name"],
            votes=int(r["votes"]),
        )
        for r in rows
    ]
    _result = WinnersMapResponse(year=year, office_code=office_code, points=points)
    agg_set(_key, _result)
    return _result


# ============================================================ RANKING NACIONAL


@router.get(
    "/stats/top-candidates",
    response_model=TopCandidatesResponse,
    summary="Ranking nacional de candidatos por votos (usa total_votes pré-computado)",
)
def top_candidates(
    ctx: CurrentTenant,
    year: int = Query(2024),
    office_code: int | None = Query(None),
    state: str | None = Query(None, min_length=2, max_length=2),
    party_number: int | None = Query(None, description="Número do partido (ex: 13 = PT)"),
    elected_only: bool = Query(False, description="So eleitos"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> TopCandidatesResponse:
    _key = f"top_cand:{year}:{office_code}:{(state or '').upper()}:{party_number}:{elected_only}:{limit}"
    _hit = agg_get(_key)
    if _hit is not None:
        return _hit

    election_ids = select(Election.id).where(Election.year == year)
    stmt = select(Candidate).where(
        Candidate.election_id.in_(election_ids),
        Candidate.total_votes.is_not(None),
    )
    if office_code is not None:
        stmt = stmt.where(Candidate.office_code == office_code)
    if state is not None:
        stmt = stmt.where(Candidate.state == state.upper())
    if party_number is not None:
        party_ids_sub = select(Party.id).where(Party.number == party_number)
        stmt = stmt.where(Candidate.party_id.in_(party_ids_sub))
    if elected_only:
        stmt = stmt.where(Candidate.result_status.like("ELEITO%"))
    stmt = stmt.order_by(Candidate.total_votes.desc()).limit(limit)
    rows = db.execute(stmt).scalars().all()

    party_ids = {c.party_id for c in rows}
    election_ids2 = {c.election_id for c in rows}
    parties_map = {
        p.id: p for p in db.execute(select(Party).where(Party.id.in_(party_ids))).scalars()
    } if party_ids else {}
    elections_map = {
        e.id: e for e in db.execute(select(Election).where(Election.id.in_(election_ids2))).scalars()
    } if election_ids2 else {}

    items = [
        RankedCandidate(
            candidate=CandidateRead(
                id=c.id,
                number=c.number,
                name=c.name,
                urn_name=c.urn_name,
                office_code=c.office_code,
                office_name=c.office_name,
                state=c.state,
                situation=c.situation,
                result_status=c.result_status,
                party=PartyRead.model_validate(parties_map[c.party_id]),
                election=ElectionRead.model_validate(elections_map[c.election_id]),
            ),
            total_votes=int(c.total_votes or 0),
        )
        for c in rows
    ]
    office_name = items[0].candidate.office_name if items else None
    _result = TopCandidatesResponse(
        year=year,
        office_code=office_code,
        office_name=office_name,
        state=state.upper() if state else None,
        items=items,
    )
    agg_set(_key, _result)
    return _result


@router.get(
    "/stats/counts",
    summary="Contagens exatas (candidatos por cargo, municípios, partidos) p/ painel",
)
def stats_counts(
    ctx: CurrentTenant,
    year: int | None = Query(None, description="Filtra candidatos por ano da eleição"),
    db: Session = Depends(get_db),
) -> dict:
    """Contagens EXATAS p/ stats — diferente de /candidates.total, que é capado
    em 5000 (otimização da busca). Agregações rápidas (count / group by)."""
    _key = f"counts:{year}"
    _hit = agg_get(_key)
    if _hit is not None:
        return _hit

    cand_q = select(func.count()).select_from(Candidate)
    office_q = select(Candidate.office_code, func.count()).group_by(Candidate.office_code)
    if year is not None:
        eids = select(Election.id).where(Election.year == year)
        cand_q = cand_q.where(Candidate.election_id.in_(eids))
        office_q = office_q.where(Candidate.election_id.in_(eids))

    candidates = int(db.execute(cand_q).scalar_one())
    by_office = {
        str(int(code)): int(n) for code, n in db.execute(office_q).all() if code is not None
    }
    municipalities = int(
        db.execute(
            select(func.count()).select_from(Municipality).where(Municipality.state != "ZZ")
        ).scalar_one()
    )
    parties = int(db.execute(select(func.count()).select_from(Party)).scalar_one())
    elections = int(db.execute(select(func.count()).select_from(Election)).scalar_one())
    _result = {
        "candidates": candidates,
        "by_office": by_office,
        "municipalities": municipalities,
        "parties": parties,
        "elections": elections,
    }
    agg_set(_key, _result)
    return _result


# ============================================================ BY ZONE


@router.get(
    "/candidates/{candidate_id}/by-zone",
    response_model=CandidateZoneVotesResponse,
    summary="Votos do candidato distribuídos por zona eleitoral",
)
def candidate_by_zone(
    candidate_id: UUID,
    ctx: CurrentTenant,
    limit: int = Query(60, ge=1, le=500),
    db: Session = Depends(get_db),
) -> CandidateZoneVotesResponse:
    _key = f"by_zone:{candidate_id}:{limit}"
    _hit = agg_get(_key)
    if _hit is not None:
        return _hit
    if db.get(Candidate, candidate_id) is None:
        raise NotFoundError("Candidato não encontrado")
    rows = db.execute(
        select(
            CandidateZoneVote.zone,
            CandidateZoneVote.votes,
            Municipality.name,
            Municipality.state,
        )
        .join(Municipality, Municipality.id == CandidateZoneVote.municipality_id)
        .where(CandidateZoneVote.candidate_id == candidate_id)
        .order_by(CandidateZoneVote.votes.desc())
        .limit(limit)
    ).all()
    items = [
        ZoneVoteItem(zone=z, municipality_name=mn, state=st, votes=int(v))
        for z, v, mn, st in rows
    ]
    _result = CandidateZoneVotesResponse(
        candidate_id=candidate_id,
        total_votes=sum(i.votes for i in items),
        items=items,
    )
    agg_set(_key, _result)
    return _result


# ============================================================ BY NEIGHBORHOOD


@router.get(
    "/candidates/{candidate_id}/by-neighborhood",
    response_model=CandidateByNeighborhoodResponse,
    summary="Votos do candidato agregados por bairro",
    description="""\
Agrega votos do candidato por bairro do local de votacao.

Pre-requisito: rodar os syncs `locais_votacao_2024` (Brasil inteiro)
e `votacao_secao_2024_<UF>` (do UF do candidato). Sem isso, retorna
lista vazia.

Filtros:
- `municipality_id` (opcional) — restringe ao municipio (util pra
  prefeitos/vereadores; pra deputados ajuda focar capital ou cidade).
""",
)
def candidate_by_neighborhood(
    candidate_id: UUID,
    ctx: CurrentTenant,
    municipality_id: UUID | None = Query(None),
    db: Session = Depends(get_db),
) -> CandidateByNeighborhoodResponse:
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise NotFoundError("Candidato nao encontrado")
    party = db.get(Party, candidate.party_id)
    election = db.get(Election, candidate.election_id)

    municipality = None
    if municipality_id is not None:
        municipality = db.get(Municipality, municipality_id)
        if municipality is None:
            raise NotFoundError("Municipio nao encontrado")

    # Agregacao SQL: JOIN section_votes × voting_places, group by bairro
    stmt = (
        select(
            func.coalesce(
                func.nullif(func.trim(TseVotingPlace.neighborhood), ""),
                "(Sem bairro)",
            ).label("neighborhood"),
            func.sum(TseSectionVote.votes).label("votes"),
            func.count(TseVotingPlace.id).label("places_count"),
            func.coalesce(func.sum(TseVotingPlace.electors_total), 0).label(
                "electors_total",
            ),
            func.avg(TseVotingPlace.latitude).label("avg_lat"),
            func.avg(TseVotingPlace.longitude).label("avg_lng"),
        )
        .join(TseVotingPlace, TseVotingPlace.id == TseSectionVote.voting_place_id)
        .where(TseSectionVote.candidate_id == candidate_id)
    )
    if municipality_id is not None:
        stmt = stmt.where(TseVotingPlace.municipality_id == municipality_id)
    stmt = stmt.group_by("neighborhood").order_by(func.sum(TseSectionVote.votes).desc())

    rows = db.execute(stmt).all()
    items = [
        CandidateByNeighborhoodItem(
            neighborhood=r.neighborhood,
            votes=int(r.votes),
            places_count=int(r.places_count),
            electors_total=int(r.electors_total),
            avg_lat=float(r.avg_lat) if r.avg_lat is not None else None,
            avg_lng=float(r.avg_lng) if r.avg_lng is not None else None,
        )
        for r in rows
    ]

    return CandidateByNeighborhoodResponse(
        candidate=CandidateRead(
            id=candidate.id,
            number=candidate.number,
            name=candidate.name,
            urn_name=candidate.urn_name,
            office_code=candidate.office_code,
            office_name=candidate.office_name,
            state=candidate.state,
            situation=candidate.situation,
            result_status=candidate.result_status,
            party=PartyRead.model_validate(party),
            election=ElectionRead.model_validate(election),
        ),
        municipality=MunicipalityRead.model_validate(municipality) if municipality else None,
        items=items,
        total_votes=sum(i.votes for i in items),
        total_neighborhoods=len(items),
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
@limiter.limit("120/minute")
def candidate_photo(
    candidate_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    # 120/min por IP — 2 fotos/seg em media. Suficiente pro fluxo normal
    # (Lista de 20 candidatos + scroll), bloqueia ataque de script.
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise NotFoundError("Candidato nao encontrado")

    # Ano da eleicao define qual zip de fotos do TSE usar (2022 vs 2024).
    election = db.get(Election, candidate.election_id)
    year = election.year if election else 2024

    # Presidente (cargo 1) e candidato NACIONAL: foto fica no zip 'BR', mas o
    # state gravado veio de um municipio (quirk do munzona). Forca BR.
    uf = "BR" if candidate.office_code == 1 else candidate.state

    try:
        jpeg = get_candidate_photo(uf, candidate.sq_candidato, year)
    except PhotoNotFound:
        # 404 cacheavel: evita re-tentar fotos inexistentes a cada visita.
        return Response(
            status_code=404,
            headers={"Cache-Control": "public, max-age=86400"},
        )

    # Negociacao de conteudo: serve WebP quando o cliente aceita (Chrome,
    # Firefox, Safari modernos suportam). Fica 40-60% menor que JPEG.
    accept = request.headers.get("accept", "")
    wants_webp = "image/webp" in accept.lower()

    if wants_webp:
        data = get_or_make_webp(uf, candidate.sq_candidato, year, jpeg)
        media = "image/webp"
        etag = f'"tse-{year}-{candidate.sq_candidato}-w"'
    else:
        data = jpeg
        media = "image/jpeg"
        etag = f'"tse-{year}-{candidate.sq_candidato}"'

    return Response(
        content=data,
        media_type=media,
        headers={
            # 30 dias — fotos sao estaveis, varia raramente
            "Cache-Control": "public, max-age=2592000, immutable",
            "ETag": etag,
            "Vary": "Accept",  # navegadores cacheiam por variante (jpeg/webp)
        },
    )


# ============================================================ DOSSIE PDF


@router.get(
    "/candidates/{candidate_id}/dossier.pdf",
    summary="Dossie PDF do candidato (executivo)",
    description="""\
Gera um PDF executivo do candidato com:
- Hero (foto, nome, partido, cargo, situacao)
- Stats (votos totais, municipios)
- Perfil rico (patrimonio, receitas, despesas, redes)
- Top 50 municipios por votos
- Top 30 zonas eleitorais por votos

Renderizado com ReportLab. ~3-5 paginas A4. Bom pra impressao e arquivo.
""",
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "PDF do dossie",
        },
        404: {"description": "Candidato nao encontrado"},
    },
    response_class=Response,
)
@limiter.limit("30/minute")
def candidate_dossier_pdf(
    candidate_id: UUID,
    request: Request,
    ctx: CurrentTenant,
    db: Session = Depends(get_db),
) -> Response:
    # 30/min por IP — gerar PDF e caro (ReportLab + QR + mapa).
    # Razoavel: 1 por 2s.
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise NotFoundError("Candidato nao encontrado")

    # --- Cache em disco ---
    # PDFs sao deterministicos. Sync do TSE deveria invalidar este cache;
    # como sync e raro, usamos tambem TTL via mtime (24h). Hit serve em ~5ms.
    from pathlib import Path as _Path
    import time as _time
    pdf_cache_dir = _Path("/var/marenostrum/pdf_cache")
    pdf_cache_path = pdf_cache_dir / f"{candidate.id}.pdf"
    if pdf_cache_path.is_file():
        try:
            age = _time.time() - pdf_cache_path.stat().st_mtime
            if age < 86400:  # 24h
                safe = "".join(
                    c if c.isalnum() else "-" for c in (candidate.urn_name or "candidato").lower()
                ).strip("-")
                fname = f"dossie-{safe}.pdf"
                return Response(
                    content=pdf_cache_path.read_bytes(),
                    media_type="application/pdf",
                    headers={
                        "Content-Disposition": f'inline; filename="{fname}"',
                        "Cache-Control": "public, max-age=86400",
                        "X-Cache": "HIT",
                    },
                )
        except Exception:
            pass  # corrupted/permission -> cai pra geracao normal

    party = db.get(Party, candidate.party_id)
    election = db.get(Election, candidate.election_id)

    # Votos por municipio (todos, ordenado desc) + coords pra mini-mapa
    muni_rows = db.execute(
        select(
            Municipality.name,
            Municipality.state,
            VoteResult.votes,
            Municipality.latitude,
            Municipality.longitude,
        )
        .join(Municipality, Municipality.id == VoteResult.municipality_id)
        .where(VoteResult.candidate_id == candidate_id)
        .order_by(VoteResult.votes.desc())
    ).all()
    municipality_results = [(n, s, int(v)) for n, s, v, _, _ in muni_rows]
    municipality_coords = [
        (float(lat) if lat is not None else None,
         float(lng) if lng is not None else None,
         int(v))
        for _, _, v, lat, lng in muni_rows
        if lat is not None and lng is not None
    ]
    total_votes = sum(v for _, _, v in municipality_results)
    muni_count = len(municipality_results)

    # Votos por zona (top 60 ja basta — usamos 30 no PDF)
    zone_rows = db.execute(
        select(
            CandidateZoneVote.zone,
            Municipality.name,
            Municipality.state,
            CandidateZoneVote.votes,
        )
        .join(Municipality, Municipality.id == CandidateZoneVote.municipality_id)
        .where(CandidateZoneVote.candidate_id == candidate_id)
        .order_by(CandidateZoneVote.votes.desc())
        .limit(60)
    ).all()
    zone_results = [(int(z), n, s, int(v)) for z, n, s, v in zone_rows]

    # Foto (best-effort — sem foto, segue sem)
    photo_bytes: bytes | None = None
    try:
        year_p = election.year if election else 2024
        uf_p = "BR" if candidate.office_code == 1 else candidate.state
        photo_bytes = get_candidate_photo(uf_p, candidate.sq_candidato, year_p)
    except Exception:
        photo_bytes = None

    pdf_bytes = build_candidate_dossier(
        candidate_name=candidate.name,
        urn_name=candidate.urn_name,
        number=candidate.number,
        office_name=candidate.office_name or "",
        state=candidate.state,
        year=election.year if election else 0,
        result_status=candidate.result_status,
        party_abbr=party.abbreviation if party else "",
        party_name=party.name if party else "",
        party_number=party.number if party else 0,
        total_votes=total_votes,
        muni_count=muni_count,
        assets_total=candidate.assets_total,
        revenue_total=candidate.revenue_total,
        expense_total=candidate.expense_total,
        social_links=candidate.social_links,
        municipality_results=municipality_results,
        zone_results=zone_results,
        photo_bytes=photo_bytes,
        candidate_id=str(candidate.id),
        public_url_base="https://srv1412083.hstgr.cloud",
        municipality_coords=municipality_coords,
    )

    # Persiste no cache (atomico via .tmp + rename)
    try:
        pdf_cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = pdf_cache_path.with_suffix(".pdf.tmp")
        tmp.write_bytes(pdf_bytes)
        tmp.replace(pdf_cache_path)
    except Exception:
        pass  # falha de cache nao impede a resposta

    # Filename amigavel pro download (sem acento/espaco)
    safe = "".join(
        c if c.isalnum() else "-" for c in (candidate.urn_name or "candidato").lower()
    ).strip("-")
    fname = f"dossie-{safe}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{fname}"',
            "Cache-Control": "public, max-age=86400",
            "X-Cache": "MISS",
        },
    )
