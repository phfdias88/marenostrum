"""
Template de mensagem (WhatsApp) reutilizável, por tenant.

Body suporta variáveis no formato {nome}, {cidade}, {bairro}, {tratamento}
— substituídas no frontend com os dados do contato antes de abrir o wa.me.
"""
from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class MessageTemplate(Base, TenantMixin, TimestampMixin):
    __tablename__ = "message_templates"

    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(String(2000), nullable=False)
    # Categoria livre: "aniversário", "convite", "agradecimento", etc.
    category: Mapped[str | None] = mapped_column(String(40), nullable=True)

    __table_args__ = (
        Index("ix_message_templates_tenant", "tenant_id", "created_at"),
    )
