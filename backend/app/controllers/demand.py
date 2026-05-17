"""
Controller de Demands.

Endpoints:
  GET    /api/v1/demands              -> lista paginada (filtros opcionais)
  POST   /api/v1/demands              -> cria
  GET    /api/v1/demands/{id}         -> detalhe
  PUT    /api/v1/demands/{id}         -> partial update
  PATCH  /api/v1/demands/{id}/status  -> atalho para mudar so' o status
  DELETE /api/v1/demands/{id}         -> hard delete
"""
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.core.dependencies import CurrentTenant
from app.models.demand import DemandStatus
from app.schemas.contact import Page
from app.schemas.demand import (
    DemandCreate,
    DemandRead,
    DemandStatusUpdate,
    DemandUpdate,
)
from app.services.demand import DemandService

router = APIRouter(prefix="/demands", tags=["demands"])


@router.get(
    "",
    response_model=Page[DemandRead],
    summary="Listar demandas (paginado, filtros opcionais por status/contato)",
)
def list_demands(
    ctx: CurrentTenant,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status_filter: DemandStatus | None = Query(None, alias="status"),
    contact_id: UUID | None = Query(None),
) -> Page[DemandRead]:
    items, total = DemandService(ctx).list_demands(
        limit=limit, offset=offset,
        status=status_filter, contact_id=contact_id,
    )
    return Page[DemandRead](
        items=[DemandRead.model_validate(d) for d in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{demand_id}",
    response_model=DemandRead,
    summary="Detalhe de uma demanda",
)
def get_demand(demand_id: UUID, ctx: CurrentTenant) -> DemandRead:
    return DemandRead.model_validate(DemandService(ctx).get_demand(demand_id))


@router.post(
    "",
    response_model=DemandRead,
    status_code=status.HTTP_201_CREATED,
    summary="Criar demanda (vinculada a um contato ativo do tenant)",
)
def create_demand(payload: DemandCreate, ctx: CurrentTenant) -> DemandRead:
    demand = DemandService(ctx).create_demand(payload)
    return DemandRead.model_validate(demand)


@router.put(
    "/{demand_id}",
    response_model=DemandRead,
    summary="Atualizar demanda (partial)",
)
def update_demand(
    demand_id: UUID, payload: DemandUpdate, ctx: CurrentTenant,
) -> DemandRead:
    demand = DemandService(ctx).update_demand(demand_id, payload)
    return DemandRead.model_validate(demand)


@router.patch(
    "/{demand_id}/status",
    response_model=DemandRead,
    summary="Atalho: mudar so' o status (usado pelo Dropdown da DataTable)",
)
def update_status(
    demand_id: UUID, payload: DemandStatusUpdate, ctx: CurrentTenant,
) -> DemandRead:
    demand = DemandService(ctx).update_demand(
        demand_id, DemandUpdate(status=payload.status),
    )
    return DemandRead.model_validate(demand)


@router.delete(
    "/{demand_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir demanda (HARD delete — use status='cancelada' pra histórico)",
)
def delete_demand(demand_id: UUID, ctx: CurrentTenant) -> Response:
    DemandService(ctx).delete_demand(demand_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
