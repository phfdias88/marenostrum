"""
Controller de templates de mensagem (WhatsApp).

CRUD simples, tenant-scoped. A substituição de variáveis ({nome}, {cidade})
acontece no frontend, com os dados do contato, antes de abrir o wa.me.
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.dependencies import CurrentTenant
from app.models.message_template import MessageTemplate
from app.schemas.message_template import (
    TemplateCreate,
    TemplateRead,
    TemplateUpdate,
)

router = APIRouter(prefix="/templates", tags=["message-templates"])


@router.get("", response_model=list[TemplateRead], summary="Listar templates")
def list_templates(ctx: CurrentTenant) -> list[TemplateRead]:
    stmt = (
        select(MessageTemplate)
        .where(MessageTemplate.tenant_id == ctx.tenant_id)
        .order_by(MessageTemplate.created_at.desc())
    )
    rows = ctx.db.execute(stmt).scalars().all()
    return [TemplateRead.model_validate(r) for r in rows]


@router.post(
    "",
    response_model=TemplateRead,
    status_code=status.HTTP_201_CREATED,
    summary="Criar template",
)
def create_template(payload: TemplateCreate, ctx: CurrentTenant) -> TemplateRead:
    t = MessageTemplate(
        tenant_id=ctx.tenant_id,
        title=payload.title,
        body=payload.body,
        category=payload.category,
    )
    ctx.db.add(t)
    ctx.db.commit()
    ctx.db.refresh(t)
    return TemplateRead.model_validate(t)


@router.put(
    "/{template_id}",
    response_model=TemplateRead,
    summary="Atualizar template",
)
def update_template(
    template_id: UUID,
    payload: TemplateUpdate,
    ctx: CurrentTenant,
) -> TemplateRead:
    t = ctx.db.get(MessageTemplate, template_id)
    if t is None or t.tenant_id != ctx.tenant_id:
        raise HTTPException(404, "Template não encontrado")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(t, k, v)
    ctx.db.commit()
    ctx.db.refresh(t)
    return TemplateRead.model_validate(t)


@router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir template",
)
def delete_template(template_id: UUID, ctx: CurrentTenant):
    t = ctx.db.get(MessageTemplate, template_id)
    if t is None or t.tenant_id != ctx.tenant_id:
        raise HTTPException(404, "Template não encontrado")
    ctx.db.delete(t)
    ctx.db.commit()
