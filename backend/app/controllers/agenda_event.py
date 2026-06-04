"""
Controller da agenda parlamentar/campanha — CRUD tenant-scoped.

Listagem com filtro opcional `upcoming` (só futuros) e ordenação por
data. Geocoding é responsabilidade do cliente (lat/lng opcional).
"""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.core.dependencies import CurrentTenant
from app.models.agenda_event import AgendaEvent
from app.schemas.agenda_event import AgendaCreate, AgendaRead, AgendaUpdate

router = APIRouter(prefix="/agenda", tags=["agenda"])


@router.get("", response_model=list[AgendaRead], summary="Listar eventos da agenda")
def list_events(
    ctx: CurrentTenant,
    upcoming: bool = Query(False, description="Só eventos a partir de agora"),
    limit: int = Query(200, ge=1, le=500),
) -> list[AgendaRead]:
    stmt = select(AgendaEvent).where(AgendaEvent.tenant_id == ctx.tenant_id)
    if upcoming:
        stmt = stmt.where(AgendaEvent.starts_at >= datetime.now(timezone.utc))
    stmt = stmt.order_by(AgendaEvent.starts_at.asc()).limit(limit)
    rows = ctx.db.execute(stmt).scalars().all()
    return [AgendaRead.model_validate(r) for r in rows]


@router.post(
    "",
    response_model=AgendaRead,
    status_code=status.HTTP_201_CREATED,
    summary="Criar evento",
)
def create_event(payload: AgendaCreate, ctx: CurrentTenant) -> AgendaRead:
    e = AgendaEvent(tenant_id=ctx.tenant_id, **payload.model_dump())
    ctx.db.add(e)
    ctx.db.commit()
    ctx.db.refresh(e)
    return AgendaRead.model_validate(e)


@router.put("/{event_id}", response_model=AgendaRead, summary="Atualizar evento")
def update_event(
    event_id: UUID, payload: AgendaUpdate, ctx: CurrentTenant
) -> AgendaRead:
    e = ctx.db.get(AgendaEvent, event_id)
    if e is None or e.tenant_id != ctx.tenant_id:
        raise HTTPException(404, "Evento não encontrado")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(e, k, v)
    ctx.db.commit()
    ctx.db.refresh(e)
    return AgendaRead.model_validate(e)


@router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir evento",
)
def delete_event(event_id: UUID, ctx: CurrentTenant):
    e = ctx.db.get(AgendaEvent, event_id)
    if e is None or e.tenant_id != ctx.tenant_id:
        raise HTTPException(404, "Evento não encontrado")
    ctx.db.delete(e)
    ctx.db.commit()
