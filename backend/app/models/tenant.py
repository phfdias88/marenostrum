"""
Tenant = candidato/cliente do SaaS.
Esta tabela NAO usa TenantMixin (e a propria raiz da arvore de isolamento).
"""
from datetime import datetime

from sqlalchemy import DateTime, String
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

    # ---- Billing (assinatura Asaas) — cache barato p/ o gating por request ----
    # 'active' por padrão: tenants LEGADOS (provisionados via seed) NUNCA são
    # bloqueados. Só tenants nascidos de compra passam por pending→active→
    # past_due→suspended→canceled (fonte da verdade = tabela subscriptions).
    subscription_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    # Janela de tolerância pós-inadimplência: enquanto now < grace_until o acesso
    # continua liberado mesmo em past_due. Nulo = sem tolerância pendente.
    grace_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
