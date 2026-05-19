"""
Controller de VotingPlace — locais de votação + heatmap eleitoral.

Endpoints:
  GET  /api/v1/voting-places          — lista paginada
  GET  /api/v1/voting-places/heatmap  — pontos pra Leaflet.heat (normalizado)
  POST /api/v1/voting-places/import   — bulk import via CSV
"""
from fastapi import APIRouter, File, Form, Query, UploadFile, status

from app.core.dependencies import CurrentTenant
from app.core.errors import DomainError
from app.schemas.contact import Page
from app.schemas.voting_place import (
    HeatmapResponse,
    NeighborhoodStatsResponse,
    VotingImportResult,
    VotingPlaceRead,
)
from app.services.voting_place import VotingPlaceService

_MAX_CSV_BYTES = 5 * 1024 * 1024


class _PayloadTooLargeError(DomainError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    code = "payload_too_large"


class _BadCsvError(DomainError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "bad_csv"


router = APIRouter(prefix="/voting-places", tags=["voting-places"])


@router.get(
    "",
    response_model=Page[VotingPlaceRead],
    summary="Listar locais de votação",
    description=(
        "Paginado, ordenado por **votos** decrescente (top performers primeiro). "
        "Filtre por `?election_year=2024` se quiser comparar pleitos."
    ),
)
def list_voting_places(
    ctx: CurrentTenant,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    election_year: int | None = Query(None, ge=1900, le=2100),
) -> Page[VotingPlaceRead]:
    items, total = VotingPlaceService(ctx).list_places(
        limit=limit, offset=offset, election_year=election_year,
    )
    return Page[VotingPlaceRead](
        items=[VotingPlaceRead.model_validate(p) for p in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/heatmap",
    response_model=HeatmapResponse,
    summary="Pontos pro heatmap eleitoral",
    description="""\
Retorna lista de pontos `{lat, lng, intensity, votes, name}` prontos pra
plugar no **Leaflet.heat**. `intensity` está normalizado em **[0, 1]**
dividindo pelo `max(votes)` do tenant.

Útil pra renderizar mapa de calor mostrando onde o candidato teve mais/menos
votos — base pra estratégia de campanha ("vou comicios no bairro com baixa
intensidade").
""",
)
def heatmap(
    ctx: CurrentTenant,
    election_year: int | None = Query(None, ge=1900, le=2100),
) -> HeatmapResponse:
    return VotingPlaceService(ctx).heatmap(election_year=election_year)


@router.get(
    "/by-neighborhood",
    response_model=NeighborhoodStatsResponse,
    summary="Agrega votos por bairro (centroide medio das coords)",
    description=(
        "Agrupa todos os locais de votacao do tenant por bairro. Bairro nulo "
        "ou vazio vira '(Sem bairro)' pra nao perder dados. Centroide "
        "(avg_lat/lng) e util pra centralizar o mapa quando clicar."
    ),
)
def by_neighborhood(
    ctx: CurrentTenant,
    election_year: int | None = Query(None, ge=1900, le=2100),
) -> NeighborhoodStatsResponse:
    return VotingPlaceService(ctx).by_neighborhood(election_year=election_year)


@router.post(
    "/import",
    response_model=VotingImportResult,
    summary="Importar locais de votação via CSV",
    description="""\
Importa em lote. Aceita CSV com cabeçalhos:

| Cabeçalho aceito | Campo |
|---|---|
| `Local de Votação`, `Nome`, `Local` | nome (obrigatório) |
| `Endereço` | endereço |
| `Bairro` | bairro |
| `Município`, `Cidade` | cidade |
| `UF`, `Estado` | UF |
| `Latitude`, `Lat` | latitude |
| `Longitude`, `Lng`, `Lon` | longitude |
| `Votos` | votos pro candidato |
| `Eleitorado`, `Total Eleitores` | eleitorado total |
| `TSE Code`, `Código TSE` | código TSE |
| `Observações`, `Obs` | observações |

### Parâmetros
- `election_year` (opcional): vincula a um pleito (2020, 2024...)
- `replace_existing=true` (default false): apaga TODOS os locais do ano
  antes de inserir — idempotência para re-upload.
""",
)
async def import_voting_csv(
    ctx: CurrentTenant,
    file: UploadFile = File(...),
    election_year: int | None = Form(None, ge=1900, le=2100),
    replace_existing: bool = Form(False),
) -> VotingImportResult:
    filename = (file.filename or "").lower()
    if not filename.endswith(".csv"):
        raise _BadCsvError("O arquivo precisa ser .csv")

    content = await file.read()
    if len(content) > _MAX_CSV_BYTES:
        raise _PayloadTooLargeError(
            f"Arquivo maior que {_MAX_CSV_BYTES // (1024 * 1024)}MB"
        )

    return VotingPlaceService(ctx).import_csv(
        content,
        election_year=election_year,
        replace_existing=replace_existing,
    )
