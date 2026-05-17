"""
Tenant = candidato/cliente do SaaS.
Esta tabela NAO usa TenantMixin (e a propria raiz da arvore de isolamento).
"""
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    # Secret usado por integrações de webhook (BotConversa, etc).
    # Nullable: tenant pode ainda não ter webhook configurado.
    # Comparação SEMPRE via hmac.compare_digest (constant-time).
    webhook_secret: Mapped[str | None] = mapped_column(String(128), nullable=True)
