"""
Controller de candidatos monitorados (meu candidato + adversarios).

Wave 2 / Onda candidato — persistencia da lista de candidatos que o
usuario acompanha. Retorna ja' com snapshot dos dados TSE pra
simplificar UI (uma chamada → uma lista renderizavel).
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.dependencies import CurrentTenant
from app.models.monitored_candidate import MonitoredCandidate
from app.models.tse import Candidate, Municipality, Party
from app.schemas.monitored_candidate import (
    MonitoredCandidateRead,
    MonitoredCreate,
    MonitoredUpdate,
)

router = APIRouter(prefix="/monitored", tags=["monitored-candidates"])


def _enrich(db, monitored: MonitoredCandidate) -> MonitoredCandidateRead:
    """Carrega snapshot do candidato TSE — None se nao existir mais."""
    cand = db.get(Candidate, monitored.candidate_id)
    party = db.get(Party, cand.party_id) if cand is not None and cand.party_id else None
    return _build_read(monitored, cand, party)


def _build_read(
    monitored: MonitoredCandidate,
    cand: Candidate | None,
    party: Party | None,
) -> MonitoredCandidateRead:
    if cand is None:
        return MonitoredCandidateRead(
            id=monitored.id,
            candidate_id=monitored.candidate_id,
            label=monitored.label,
            is_mine=monitored.is_mine,
            color=monitored.color,
            notes=monitored.notes,
            created_at=monitored.created_at,
            candidate_found=False,
        )
    # tse_candidates nao tem direct FK pra municipality;
    # municipality_id existe em vote_results. Aqui retornamos None — UI
    # mostra "UF" suficiente.
    return MonitoredCandidateRead(
        id=monitored.id,
        candidate_id=monitored.candidate_id,
        label=monitored.label,
        is_mine=monitored.is_mine,
        color=monitored.color,
        notes=monitored.notes,
        created_at=monitored.created_at,
        candidate_found=True,
        candidate_name=cand.urn_name or cand.name,
        candidate_number=cand.number,
        candidate_party_abbr=party.abbreviation if party else None,
        candidate_office_name=cand.office_name,
        candidate_state=cand.state,
        candidate_municipality_name=None,
        candidate_total_votes=cand.total_votes,
        candidate_was_elected=(cand.result_status or "").upper().startswith("ELEITO")
        if cand.result_status
        else None,
    )


@router.get(
    "",
    response_model=list[MonitoredCandidateRead],
    summary="Listar candidatos monitorados",
    description="Retorna meu candidato + adversarios com snapshot TSE.",
)
def list_monitored(ctx: CurrentTenant) -> list[MonitoredCandidateRead]:
    stmt = (
        select(MonitoredCandidate)
        .where(MonitoredCandidate.tenant_id == ctx.tenant_id)
        # is_mine primeiro, depois ordem de criacao
        .order_by(
            MonitoredCandidate.is_mine.desc(),
            MonitoredCandidate.created_at.asc(),
        )
    )
    rows = list(ctx.db.execute(stmt).scalars().all())
    # Batch-load (anti N+1): 2 queries pra lista inteira em vez de 2 por item.
    cand_ids = [m.candidate_id for m in rows]
    cands = {
        c.id: c for c in ctx.db.execute(
            select(Candidate).where(Candidate.id.in_(cand_ids))
        ).scalars()
    } if cand_ids else {}
    party_ids = {c.party_id for c in cands.values() if c.party_id}
    parties = {
        p.id: p for p in ctx.db.execute(
            select(Party).where(Party.id.in_(party_ids))
        ).scalars()
    } if party_ids else {}
    return [
        _build_read(
            m,
            cands.get(m.candidate_id),
            parties.get(cands[m.candidate_id].party_id)
            if m.candidate_id in cands and cands[m.candidate_id].party_id else None,
        )
        for m in rows
    ]


@router.post(
    "",
    response_model=MonitoredCandidateRead,
    status_code=status.HTTP_201_CREATED,
    summary="Adicionar candidato à lista monitorada",
)
def add_monitored(
    payload: MonitoredCreate,
    ctx: CurrentTenant,
) -> MonitoredCandidateRead:
    # Valida que o candidato existe no TSE
    cand = ctx.db.get(Candidate, payload.candidate_id)
    if cand is None:
        raise HTTPException(404, "Candidato TSE nao encontrado.")

    # Se marcar is_mine=True, desmarcar qualquer outro is_mine do tenant
    if payload.is_mine:
        existing_mine_stmt = select(MonitoredCandidate).where(
            MonitoredCandidate.tenant_id == ctx.tenant_id,
            MonitoredCandidate.is_mine.is_(True),
        )
        for prev in ctx.db.execute(existing_mine_stmt).scalars().all():
            prev.is_mine = False

    m = MonitoredCandidate(
        tenant_id=ctx.tenant_id,
        candidate_id=payload.candidate_id,
        label=payload.label,
        is_mine=payload.is_mine,
        color=payload.color,
        notes=payload.notes,
    )
    ctx.db.add(m)
    try:
        ctx.db.commit()
    except IntegrityError:
        ctx.db.rollback()
        raise HTTPException(409, "Candidato ja' esta na sua lista monitorada.")
    ctx.db.refresh(m)
    return _enrich(ctx.db, m)


@router.patch(
    "/{monitored_id}",
    response_model=MonitoredCandidateRead,
    summary="Atualizar metadados (label/cor/is_mine)",
)
def update_monitored(
    monitored_id: UUID,
    payload: MonitoredUpdate,
    ctx: CurrentTenant,
) -> MonitoredCandidateRead:
    m = ctx.db.get(MonitoredCandidate, monitored_id)
    if m is None or m.tenant_id != ctx.tenant_id:
        raise HTTPException(404, "Nao encontrado.")

    # Promovendo a 'meu candidato' → desmarcar atual
    if payload.is_mine is True and not m.is_mine:
        existing_mine_stmt = select(MonitoredCandidate).where(
            MonitoredCandidate.tenant_id == ctx.tenant_id,
            MonitoredCandidate.is_mine.is_(True),
            MonitoredCandidate.id != m.id,
        )
        for prev in ctx.db.execute(existing_mine_stmt).scalars().all():
            prev.is_mine = False

    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(m, k, v)
    ctx.db.commit()
    ctx.db.refresh(m)
    return _enrich(ctx.db, m)


@router.delete(
    "/{monitored_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remover candidato da lista monitorada",
)
def delete_monitored(monitored_id: UUID, ctx: CurrentTenant):
    m = ctx.db.get(MonitoredCandidate, monitored_id)
    if m is None or m.tenant_id != ctx.tenant_id:
        raise HTTPException(404, "Nao encontrado.")
    ctx.db.delete(m)
    ctx.db.commit()
