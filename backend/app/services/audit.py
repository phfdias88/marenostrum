"""
Helper de auditoria — registra create/update/delete na trilha (audit_logs).

`record_audit` apenas ADICIONA a linha na sessão atual; o commit acontece
junto com a operação que está sendo auditada (consistência: ou grava os dois,
ou nenhum). Nunca deve quebrar a operação principal — por isso engole
qualquer erro e só loga.
"""
from __future__ import annotations

from uuid import UUID

import structlog

from app.core.tenant_context import TenantContext
from app.models.audit_log import AuditLog

log = structlog.get_logger("marenostrum.audit")


def record_audit(
    ctx: TenantContext,
    *,
    action: str,
    entity_type: str,
    entity_id: UUID | None = None,
    summary: str | None = None,
    meta: dict | None = None,
) -> None:
    """Anexa um registro de auditoria à sessão (committed junto da operação)."""
    try:
        ctx.db.add(
            AuditLog(
                tenant_id=ctx.tenant_id,
                user_id=ctx.user_id,
                user_name=(ctx.user_name or None),
                user_role=ctx.role,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                summary=(summary or None),
                meta=meta,
            )
        )
    except Exception as e:  # pragma: no cover - auditoria nunca derruba a ação
        log.warning("audit_record_failed", err=str(e)[:200])
