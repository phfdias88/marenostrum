"""
Controller TSE — sync + leitura de dados públicos eleitorais.

Endpoints autenticados (qualquer usuário com JWT vê os mesmos dados —
não há filtro de tenant porque dados TSE são públicos).
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status
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
    CandidateZoneVotesResponse,
    ElectionRead,
    ElectionStatsResponse,
    ElectorateResponse,
    ZoneTopCandidate,
    ZoneVoteItem,
    MunicipalityRead,
    MunicipalityResultsResponse,
    MunicipalityZone,
    MunicipalityZonesResponse,
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
    year: int | None = Query(None, description="Ano da eleição (2024, 2022...)"),
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
        # Busca acento-insensível: f_unaccent(coluna) ILIKE f_unaccent(termo).
        # Indexes funcionais GIN trigram em f_unaccent(...) mantêm rápido.
        term = func.f_unaccent(f"%{search}%")
        stmt = stmt.where(
            func.f_unaccent(Candidate.name).ilike(term)
            | func.f_unaccent(Candidate.urn_name).ilike(term)
        )

    if party_number is not None:
        party_id_subq = select(Party.id).where(Party.number == party_number)
        stmt = stmt.where(Candidate.party_id.in_(party_id_subq))

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
    muni = db.get(Municipality, municipality_id)
    if muni is None:
        raise NotFoundError("Município não encontrado")

    election_ids = select(Election.id).where(Election.year == year)
    rows = db.execute(
        select(CandidateZoneVote.zone, CandidateZoneVote.votes, Candidate)
        .join(Candidate, Candidate.id == CandidateZoneVote.candidate_id)
        .where(
            CandidateZoneVote.municipality_id == municipality_id,
            Candidate.office_code == office_code,
            Candidate.election_id.in_(election_ids),
        )
        .order_by(CandidateZoneVote.zone, CandidateZoneVote.votes.desc())
    ).all()

    # Agrupa por zona (já vem ordenado por zona, votos desc)
    parties_cache: dict[UUID, Party] = {}
    elections_cache: dict[UUID, Election] = {}
    zones_map: dict[int, dict] = {}
    for zone, votes, cand in rows:
        z = zones_map.setdefault(zone, {"total": 0, "cands": []})
        z["total"] += int(votes)
        if len(z["cands"]) < top_per_zone:
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
    return MunicipalityZonesResponse(
        municipality=MunicipalityRead.model_validate(muni),
        office_code=office_code,
        office_name=office_name,
        zones=zones,
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
    return CandidateZoneVotesResponse(
        candidate_id=candidate_id,
        total_votes=sum(i.votes for i in items),
        items=items,
    )


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
def candidate_photo(
    candidate_id: UUID,
    db: Session = Depends(get_db),
) -> Response:
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
        data = get_candidate_photo(uf, candidate.sq_candidato, year)
    except PhotoNotFound:
        # 404 cacheável: evita re-tentar fotos inexistentes a cada visita.
        # 1 dia (mais curto que as existentes — foto pode ser publicada depois).
        return Response(
            status_code=404,
            headers={"Cache-Control": "public, max-age=86400"},
        )

    return Response(
        content=data,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=604800",  # 7 dias
            "ETag": f'"tse-{year}-{candidate.sq_candidato}"',
        },
    )
