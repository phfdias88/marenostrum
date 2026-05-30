"""
Controller (router FastAPI) de contatos.

Responsabilidades:
- Mapear HTTP <-> Schemas Pydantic
- Resolver `CurrentTenant` (JWT + sessão + tenant_id)
- Injetar `BackgroundTasks` quando endpoint pode disparar geocoding
- Delegar pro Service. NUNCA contém regra de negócio nem fala com ORM.
"""
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, File, Query, Response, UploadFile, status

from app.core.dependencies import CurrentTenant
from app.core.errors import DomainError
from app.schemas.contact import (
    BirthdayContact,
    ContactCreate,
    ContactRead,
    ContactUpdate,
    ImportResult,
    Page,
    TagItem,
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
    summary="Listar contatos do tenant",
    description="""\
Lista paginada de contatos **ativos** do tenant logado.

### Filtros
- `?search=joão` — busca **case-insensitive** parcial no nome (ILIKE)
- `?limit=N&offset=N` — paginação (limit max=100)

### Ordenação
Mais recentes primeiro (`created_at DESC`).

### Soft delete
Contatos com `is_active=false` (soft-deleted) **NÃO** aparecem aqui.
""",
)
def list_contacts(
    ctx: CurrentTenant,
    limit: int = Query(50, ge=1, le=100, description="Itens por página"),
    offset: int = Query(0, ge=0, description="Pular N itens"),
    search: str | None = Query(
        None,
        max_length=120,
        description="Filtro ILIKE no nome (case-insensitive, busca parcial)",
        examples=["joão", "silva"],
    ),
    tag: str | None = Query(
        None,
        max_length=32,
        description="Filtro por tag exata (use /contacts/tags pra listar disponíveis)",
        examples=["doador-2024", "lideranca"],
    ),
) -> Page[ContactRead]:
    items, total = ContactService(ctx).list_contacts(
        limit=limit, offset=offset, search=search, tag=tag,
    )
    return Page[ContactRead](
        items=[ContactRead.model_validate(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------- Tags


@router.get(
    "/tags",
    response_model=list[TagItem],
    summary="Listar tags usadas + contagem",
    description=(
        "Retorna tags distintas usadas em contatos ATIVOS do tenant, "
        "ordenadas por uso (DESC). Frontend usa pra chips/autocomplete."
    ),
)
def list_tags(ctx: CurrentTenant) -> list[TagItem]:
    return ContactService(ctx).list_tag_summary()


# ------------------------------------------------------- Aniversariantes


@router.get(
    "/birthdays",
    response_model=list[BirthdayContact],
    summary="Aniversariantes (hoje ou janela futura)",
    description="""\
Lista contatos ATIVOS aniversariando entre hoje e hoje+`days_ahead`.

### Parâmetros
- `days_ahead=0` (default) — só hoje
- `days_ahead=6` — hoje + próximos 6 dias (semana inteira)
- `days_ahead=29` — próximos 30 dias (mês)

Ordenado por `days_until` ASC, depois nome.
""",
)
def list_birthdays(
    ctx: CurrentTenant,
    days_ahead: int = Query(0, ge=0, le=60, description="Dias à frente (0=hoje)"),
) -> list[BirthdayContact]:
    return ContactService(ctx).list_birthdays(days_ahead=days_ahead)


@router.get(
    "/map",
    response_model=list[ContactRead],
    summary="Contatos com coordenadas (para o mapa)",
    description=(
        "Retorna **apenas** contatos com `latitude` E `longitude` preenchidos. "
        "Usado pelo `/dashboard/map` no frontend. Contatos soft-deleted são excluídos."
    ),
)
def list_contacts_for_map(ctx: CurrentTenant) -> list[ContactRead]:
    contacts = ContactService(ctx).list_for_map()
    return [ContactRead.model_validate(c) for c in contacts]


# --------------------------------------------------------- Interactions


@router.get(
    "/{contact_id}/interactions",
    response_model=Page[InteractionRead],
    summary="Timeline de interações do contato",
    description="""\
Lista paginada de **eventos externos** (webhooks BotConversa, SMS, etc)
vinculados a este contato.

Ordem: mais recentes primeiro (`created_at DESC`).

### Erros
- **404** se o contato não pertence ao seu tenant (defesa multi-tenant).
  Mesmo que você "adivinhe" um UUID válido de outro tenant, retorna 404.
""",
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


# ------------------------------------------------------------------ Detail


@router.get(
    "/{contact_id}",
    response_model=ContactRead,
    summary="Detalhe de um contato",
    description=(
        "Retorna 404 se o contato não existir, foi soft-deletado, "
        "ou pertence a outro tenant (anti enumeration)."
    ),
)
def get_contact(contact_id: UUID, ctx: CurrentTenant) -> ContactRead:
    return ContactRead.model_validate(ContactService(ctx).get_contact(contact_id))


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
    summary="Importar contatos em lote via CSV",
    description="""\
Importa contatos em **lote** via CSV. Sem geocoding (seria 1 req/s no Nominatim,
levaria ~17 min pra 1000 contatos — rodaremos como job de lote futuro).

### Cabeçalhos aceitos
PT-BR ou EN, com normalização (case-insensitive, sem acento):

| Coluna | Campo |
|---|---|
| Nome (obrigatório) | `full_name` |
| Telefone, Celular | `phone` |
| Email | `email` |
| Endereço | `address` |
| Bairro | `neighborhood` |
| Cidade | `city` |
| UF, Estado | `state` |
| Nascimento, Aniversário | `birth_date` (DD/MM/AAAA ou ISO) |
| Tipo | `type` (Eleitor/Liderança/Apoiador/Doador/Outro) |
| Observações, Obs | `notes` |

### Dialeto
Detectado automaticamente (`,` ou `;` — Excel pt-BR usa `;`).

### Encoding
UTF-8 com ou sem BOM (Excel pt-BR salva com BOM), fallback latin-1.

### Estratégia anti-duplicata
1. Dedup intra-arquivo por telefone
2. Query única buscando telefones já existentes no tenant
3. Bulk insert apenas do que sobrou

### Limites
- Tamanho máximo: 5 MB (~ 50k linhas)
""",
)
async def import_contacts(
    ctx: CurrentTenant,
    file: UploadFile = File(..., description="Arquivo .csv com cabeçalhos"),
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


# ------------------------------------------------------------------ Create


@router.post(
    "",
    response_model=ContactRead,
    status_code=status.HTTP_201_CREATED,
    summary="Criar contato",
    description="""\
Cria um contato no CRM do **seu** tenant (vem do JWT).

### Validação
- `full_name` obrigatório (mín. 2 chars)
- `phone` único **por tenant** (mesmo número pode existir em campanhas diferentes)
- `email` valida formato

### Geocoding em background
Se você **não** fornecer `latitude`/`longitude` mas fornecer endereço,
o backend dispara uma `BackgroundTask` que consulta o Nominatim
(rate-limited 1 req/s) e atualiza o contato silenciosamente.

Resposta vem com `latitude: null, longitude: null` — coordenadas chegam
em segundos via background.

### Erros
- **409** se telefone já cadastrado (mesmo se contato foi soft-deletado)
- **422** se validação Pydantic falhar (nome curto, email inválido, etc)
""",
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
    summary="Atualizar contato (partial)",
    description="""\
Atualização **parcial** — só campos enviados são alterados, resto preservado.

### Re-geocoding inteligente
Se você alterar `address`/`neighborhood`/`city`/`state` **e não** enviar
`latitude`/`longitude` novos, o backend re-geocoda em background.

Se enviar coords explícitas, elas têm precedência e não disparam geocoding.
""",
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
    summary="Excluir contato (soft delete)",
    description="""\
**Soft delete** — marca `is_active=false`. Cliente vê o mesmo comportamento
(some das listas, GET retorna 404), mas:

- Linha **preserva no DB** (auditoria)
- `Interaction` e `Demand` que referenciam continuam válidas
- Telefone **continua bloqueando** novo cadastro (unique constraint do DB
  inclui inactive — decisão conservadora)

Pra LGPD/direito ao esquecimento, um endpoint `purge` separado seria
necessário (não implementado).
""",
)
def delete_contact(contact_id: UUID, ctx: CurrentTenant) -> Response:
    ContactService(ctx).delete_contact(contact_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
