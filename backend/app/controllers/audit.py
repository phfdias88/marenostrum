"""
Controller da trilha de auditoria (nível Mare Nostrum).

Lista quem fez o quê (create/update/delete) no tenant. Restrito ao owner
(Administrador/Dono) — e, no futuro, ao papel "Mare Nostrum". Cada campanha só
enxerga os próprios registros (filtro por tenant_id).
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import CurrentTenant
from app.core.errors import DomainError
from app.models.audit_log import AuditLog
from app.schemas.audit import AuditLogItem, AuditLogList

router = APIRouter(prefix="/audit", tags=["audit"])


class _ForbiddenError(DomainError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


# Papéis que podem VER a auditoria. "mare_nostrum" entra quando o papel for
# criado; por ora só o owner (Administrador/Dono).
_AUDIT_VIEWERS = {"owner", "mare_nostrum"}


@router.get(
    "",
    response_model=AuditLogList,
    summary="Trilha de auditoria do tenant (quem fez o quê)",
    description=(
        "Lista as ações registradas (cadastro/edição/exclusão de contatos e "
        "usuários, mudanças de papel/senha/acesso) com quem fez e quando. "
        "Restrito ao Administrador (Dono). Filtros opcionais por tipo de "
        "entidade e ação."
    ),
)
def list_audit(
    ctx: CurrentTenant,
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    entity_type: str | None = Query(None, description="contact | user | ..."),
    action: str | None = Query(None, description="create | update | delete"),
    user_id: UUID | None = Query(None, description="filtra por quem fez"),
) -> AuditLogList:
    if (ctx.role or "").lower() not in _AUDIT_VIEWERS:
        raise _ForbiddenError(
            "Só o Administrador (Dono) pode ver a trilha de auditoria."
        )

    filters = [AuditLog.tenant_id == ctx.tenant_id]
    if entity_type:
        filters.append(AuditLog.entity_type == entity_type)
    if action:
        filters.append(AuditLog.action == action)
    if user_id:
        filters.append(AuditLog.user_id == user_id)

    total = int(
        db.execute(select(func.count()).select_from(AuditLog).where(*filters)).scalar()
        or 0
    )
    rows = db.execute(
        select(AuditLog)
        .where(*filters)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()

    return AuditLogList(
        items=[AuditLogItem.model_validate(r) for r in rows],
        total=total,
    )
