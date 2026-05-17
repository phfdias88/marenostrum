"""
Controller (router FastAPI) de contatos.

Responsabilidades:
- Mapear HTTP <-> Schemas Pydantic
- Resolver `CurrentTenant` (JWT + sessao + tenant_id)
- Injetar `BackgroundTasks` quando endpoint pode disparar geocoding
- Delegar pro Service. NUNCA contem regra de negocio nem fala com ORM.
"""
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Query, Response, status

from app.core.dependencies import CurrentTenant
from app.schemas.contact import (
    ContactCreate,
    ContactRead,
    ContactUpdate,
    Page,
)
from app.services.contact import ContactService

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


# ------------------------------------------------------------------ Delete


@router.delete(
    "/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remover contato",
)
def delete_contact(contact_id: UUID, ctx: CurrentTenant) -> Response:
    ContactService(ctx).delete_contact(contact_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
