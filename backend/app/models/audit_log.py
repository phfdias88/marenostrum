"""
Log de auditoria — registra QUEM (usuário) fez O QUÊ (create/update/delete) em
qual ENTIDADE, com um resumo legível e metadados opcionais.

Imutável (sem updated_at). É a base do nível "Mare Nostrum": permite rastrear
quem alterou/excluiu cada coisa, caso alguém faça besteira. Multi-tenant —
cada campanha só vê os próprios registros.
"""
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin


class AuditLog(Base, TenantMixin):
    __tablename__ = "audit_logs"

    # Quem fez. SET NULL se o usuário for removido — o nome/role denormalizado
    # preserva a trilha mesmo assim.
    user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    user_role: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # O quê: create | update | delete (string livre p/ extensão futura).
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    # Em qual entidade: contact | user | demand | agenda | ...
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)

    # Resumo legível ("Cadastrou contato João da Silva") + metadados (campos
    # alterados, valores antigos/novos, etc).
    summary: Mapped[str | None] = mapped_column(String(300), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_audit_logs_tenant_created", "tenant_id", "created_at"),
        Index("ix_audit_logs_tenant_entity", "tenant_id", "entity_type"),
    )
