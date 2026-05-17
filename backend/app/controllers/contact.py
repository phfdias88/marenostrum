"""
Controller (router FastAPI) de contatos.

Responsabilidades:
- Mapear HTTP <-> Schemas Pydantic
- Resolver `CurrentTenant` (JWT + sessao + tenant_id)
- Delegar para o Service
NUNCA contem regra de negocio nem fala com o ORM direto.
"""
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

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
    summary="Listar contatos (paginado, filtrado por tenant)",
)
def list_contacts(
    ctx: CurrentTenant,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> Page[ContactRead]:
    items, total = ContactService(ctx).list_contacts(limit=limit, offset=offset)
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
    summary="Criar contato no CRM",
)
def create_contact(payload: ContactCreate, ctx: CurrentTenant) -> ContactRead:
    contact = ContactService(ctx).create_contact(payload)
    return ContactRead.model_validate(contact)


# ------------------------------------------------------------------ Update


@router.put(
    "/{contact_id}",
    response_model=ContactRead,
    summary="Atualizar contato (partial update)",
)
def update_contact(
    contact_id: UUID,
    payload: ContactUpdate,
    ctx: CurrentTenant,
) -> ContactRead:
    contact = ContactService(ctx).update_contact(contact_id, payload)
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
