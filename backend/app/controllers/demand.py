"""
Controller de Demands (gabinete).

Endpoints:
  GET    /api/v1/demands              -> lista paginada (filtros opcionais)
  POST   /api/v1/demands              -> cria (contact_id obrigatório)
  GET    /api/v1/demands/{id}         -> detalhe
  PUT    /api/v1/demands/{id}         -> partial update
  PATCH  /api/v1/demands/{id}/status  -> atalho para mudar só o status
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


# Registrada ANTES das rotas /{demand_id}: senão GET /demands/stats casaria o
# path param e viraria 422 (demand_id="stats" não é UUID).
@router.get(
    "/stats",
    summary="Contagem de demandas por status (KPIs do dashboard)",
    description=(
        "Um único GROUP BY devolvendo {aberta, em_andamento, resolvida, "
        "cancelada}. O overview fazia 3 requests separados só pra contar."
    ),
)
def demand_stats(ctx: CurrentTenant) -> dict[str, int]:
    return DemandService(ctx).stats_by_status()


@router.get(
    "",
    response_model=Page[DemandRead],
    summary="Listar demandas (paginado, filtros opcionais)",
    description="""\
Lista paginada de demandas do tenant.

### Filtros
- `?status=aberta` — `aberta` | `em_andamento` | `resolvida` | `cancelada`
- `?contact_id=<uuid>` — todas demandas de um contato específico
- `?open_older_than_days=15` — só ABERTAS/EM ANDAMENTO criadas há **+N dias**
  (aging: chip "Paradas +15d" na UI)
- `?limit=N&offset=N` — paginação

Cada item vem com `contact: {id, full_name}` aninhado (joinedload, sem N+1).
""",
)
def list_demands(
    ctx: CurrentTenant,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status_filter: DemandStatus | None = Query(
        None, alias="status",
        description="Filtrar por status",
    ),
    contact_id: UUID | None = Query(
        None,
        description="Filtrar pelas demandas de um contato específico (do seu tenant)",
    ),
    open_older_than_days: int | None = Query(
        None, ge=1, le=365,
        description=(
            "Aging: só demandas ABERTAS/EM ANDAMENTO criadas há mais de N dias"
        ),
    ),
) -> Page[DemandRead]:
    items, total = DemandService(ctx).list_demands(
        limit=limit, offset=offset,
        status=status_filter, contact_id=contact_id,
        open_older_than_days=open_older_than_days,
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
    summary="Criar demanda",
    description="""\
Cria demanda vinculada a um **contato ATIVO** do seu tenant.

### Validação anti cross-tenant
O backend valida que `contact_id` pertence ao **seu** tenant **antes** de inserir.
Se você "adivinhar" um UUID válido de contato de outro tenant, retorna **404** —
mesma resposta que pra contato inexistente (anti enumeration).

### Status inicial sugerido
`aberta` (default). Use `PATCH /{id}/status` depois pra mover via Dropdown na UI.
""",
)
def create_demand(payload: DemandCreate, ctx: CurrentTenant) -> DemandRead:
    demand = DemandService(ctx).create_demand(payload)
    return DemandRead.model_validate(demand)


@router.put(
    "/{demand_id}",
    response_model=DemandRead,
    summary="Atualizar demanda (partial)",
    description=(
        "Atualização parcial. `contact_id` é **imutável** — pra "
        "vincular a outro contato, exclua e crie uma nova."
    ),
)
def update_demand(
    demand_id: UUID, payload: DemandUpdate, ctx: CurrentTenant,
) -> DemandRead:
    demand = DemandService(ctx).update_demand(demand_id, payload)
    return DemandRead.model_validate(demand)


@router.patch(
    "/{demand_id}/status",
    response_model=DemandRead,
    summary="Mudar status (atalho)",
    description=(
        "Atalho semântico pra um único campo (`status`). Usado pelo "
        "Dropdown rápido da DataTable no frontend, com optimistic update."
    ),
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
    summary="Excluir demanda (HARD delete)",
    description="""\
**Hard delete** — registro removido permanentemente.

Pra **manter histórico**, use o status `cancelada` em vez de excluir.
Isso preserva o registro pra relatórios futuros.
""",
)
def delete_demand(demand_id: UUID, ctx: CurrentTenant) -> Response:
    DemandService(ctx).delete_demand(demand_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
