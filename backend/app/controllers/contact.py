"""
Controller (router FastAPI) de contatos.

Responsabilidades:
- Mapear HTTP <-> Schemas Pydantic
- Resolver `CurrentTenant` (JWT + sessao + tenant_id)
- Injetar `BackgroundTasks` quando endpoint pode disparar geocoding
- Delegar pro Service. NUNCA contem regra de negocio nem fala com ORM.
"""
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, File, Query, Response, UploadFile, status

from app.core.dependencies import CurrentTenant
from app.core.errors import DomainError
from app.schemas.contact import (
    ContactCreate,
    ContactRead,
    ContactUpdate,
    ImportResult,
    Page,
)
from app.schemas.interaction import InteractionRead
from app.services.contact import ContactService

# Limite defensivo de tamanho do upload (~5MB ~ 50k linhas).
# Nginx tambem limita via client_max_body_size 10m, mas validamos aqui pra
# devolver erro amigavel antes de carregar tudo na memoria.
_MAX_CSV_BYTES = 5 * 1024 * 1024

router = APIRouter(prefix="/contacts", tags=["contacts"])


# -------------------------------------------------------------------- List


@router.get(
    "",
    response_model=Page[ContactRead],
    summary="Listar contatos (paginado, busca por nome opcional)",
)
def list_contacts(
    ctx: CurrentTenant,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: str | None = Query(
        None,
        max_length=120,
        description="Filtro ILIKE no nome (case-insensitive, busca parcial)",
    ),
) -> Page[ContactRead]:
    items, total = ContactService(ctx).list_contacts(
        limit=limit, offset=offset, search=search,
    )
    return Page[ContactRead](
        items=[ContactRead.model_validate(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/map",
    response_model=list[ContactRead],
    summary="Lista contatos com lat/lng preenchidos (para o mapa)",
)
def list_contacts_for_map(ctx: CurrentTenant) -> list[ContactRead]:
    contacts = ContactService(ctx).list_for_map()
    return [ContactRead.model_validate(c) for c in contacts]


# ------------------------------------------------------------------ Detail


@router.get(
    "/{contact_id}",
    response_model=ContactRead,
    summary="Detalhe de um contato",
)
def get_contact(contact_id: UUID, ctx: CurrentTenant) -> ContactRead:
    return ContactRead.model_validate(ContactService(ctx).get_contact(contact_id))


# ------------------------------------------------------------------ Create


@router.post(
    "",
    response_model=ContactRead,
    status_code=status.HTTP_201_CREATED,
    summary="Criar contato (geocoda em background se faltar lat/lng)",
)
def create_contact(
    payload: ContactCreate,
    ctx: CurrentTenant,
    background_tasks: BackgroundTasks,
) -> ContactRead:
    contact = ContactService(ctx).create_contact(payload, background_tasks)
    return ContactRead.model_validate(contact)


# --------------------------------------------------------- Interactions


@router.get(
    "/{contact_id}/interactions",
    response_model=Page[InteractionRead],
    summary="Timeline de interações do contato (webhooks recebidos)",
)
def list_contact_interactions(
    contact_id: UUID,
    ctx: CurrentTenant,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Page[InteractionRead]:
    items, total = ContactService(ctx).list_contact_interactions(
        contact_id, limit=limit, offset=offset,
    )
    return Page[InteractionRead](
        items=[InteractionRead.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ------------------------------------------------------------------ Update


@router.put(
    "/{contact_id}",
    response_model=ContactRead,
    summary="Atualizar contato (re-geocoda se endereço mudou e sem coords)",
)
def update_contact(
    contact_id: UUID,
    payload: ContactUpdate,
    ctx: CurrentTenant,
    background_tasks: BackgroundTasks,
) -> ContactRead:
    contact = ContactService(ctx).update_contact(contact_id, payload, background_tasks)
    return ContactRead.model_validate(contact)


# ------------------------------------------------------------------ Import


class _PayloadTooLargeError(DomainError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    code = "payload_too_large"


class _BadCsvError(DomainError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "bad_csv"


@router.post(
    "/import",
    response_model=ImportResult,
    summary="Importar contatos em lote via CSV (sem geocoding)",
)
async def import_contacts(
    ctx: CurrentTenant,
    file: UploadFile = File(..., description="Arquivo .csv com cabecalhos"),
) -> ImportResult:
    # Validacao basica do upload
    filename = (file.filename or "").lower()
    if not filename.endswith(".csv"):
        raise _BadCsvError("O arquivo precisa ser .csv")

    # Le bytes — checa tamanho conforme le pra nao explodir RAM em VPS pequena
    content = await file.read()
    if len(content) > _MAX_CSV_BYTES:
        raise _PayloadTooLargeError(
            f"Arquivo maior que {_MAX_CSV_BYTES // (1024 * 1024)}MB"
        )

    return ContactService(ctx).import_csv_contacts(content)


# ------------------------------------------------------------------ Delete


@router.delete(
    "/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remover contato",
)
def delete_contact(contact_id: UUID, ctx: CurrentTenant) -> Response:
    ContactService(ctx).delete_contact(contact_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
