"""
Controller (router FastAPI) de contatos.

Responsabilidades unicas:
- Mapear HTTP <-> Schemas Pydantic
- Resolver dependencias (CurrentTenant)
- Delegar para o Service
NAO contem regra de negocio. NAO acessa o ORM diretamente.
"""
from fastapi import APIRouter, Query, status

from app.core.dependencies import CurrentTenant
from app.schemas.contact import ContactCreate, ContactRead
from app.services.contact import ContactService

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get(
    "",
    response_model=list[ContactRead],
    summary="Listar contatos do tenant atual",
)
def list_contacts(
    ctx: CurrentTenant,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[ContactRead]:
    contacts = ContactService(ctx).list_contacts(limit=limit, offset=offset)
    return [ContactRead.model_validate(c) for c in contacts]


@router.post(
    "",
    response_model=ContactRead,
    status_code=status.HTTP_201_CREATED,
    summary="Criar um novo contato no CRM politico",
)
def create_contact(
    payload: ContactCreate,
    ctx: CurrentTenant,
) -> ContactRead:
    """
    Cria um contato vinculado AUTOMATICAMENTE ao tenant do usuario logado.
    O cliente nao pode enviar tenant_id - ele e ignorado por design (o schema
    sequer aceita esse campo).
    """
    service = ContactService(ctx)
    contact = service.create_contact(payload)
    return ContactRead.model_validate(contact)
