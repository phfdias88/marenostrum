"""
Billing recorrente (Asaas) — assinatura mensal do produto vendido no site.

Duas tabelas:
- `subscriptions`: uma linha por assinatura criada no checkout. Nasce ANTES do
  tenant existir (status='pending'); quando o 1º pagamento confirma, o webhook
  provisiona o tenant e liga tenant_id + status='active'. Por isso tenant_id é
  NULLABLE (não usa TenantMixin, que exige não-nulo).
- `billing_events`: idempotência do webhook. O Asaas entrega "pelo menos uma
  vez" (at-least-once); sem dedup por event id, o mesmo pagamento provisionaria
  o tenant duas vezes. INSERT do event id numa UNIQUE = trava natural.

Tipos cross-DB (sa.Uuid, JSON().with_variant(JSONB)) pra não quebrar o
create_all do SQLite no pytest — mesma regra do resto do projeto.
"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

_JSONB = JSON().with_variant(JSONB, "postgresql")

# Status da assinatura (string, não enum Postgres — sobrevive ao SQLite do pytest):
#   pending   → assinatura criada, 1ª fatura não paga (tenant ainda não existe)
#   active    → em dia (paga)
#   past_due  → venceu, dentro da janela de tolerância (grace) — ainda entra
#   suspended → grace expirou → acesso bloqueado (402)
#   canceled  → assinatura deletada/inativada
SUBSCRIPTION_STATUSES = ("pending", "active", "past_due", "suspended", "canceled")


class Subscription(Base, TimestampMixin):
    __tablename__ = "subscriptions"

    # Nullable: a assinatura existe antes do tenant (o webhook provisiona depois).
    tenant_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    # Ids do Asaas.
    asaas_customer_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    asaas_subscription_id: Mapped[str | None] = mapped_column(
        String(40), nullable=True, unique=True, index=True
    )
    # Nosso elo Asaas↔nós, mandado como externalReference no checkout e devolvido
    # no payload do webhook — casa o pagamento com esta linha.
    external_reference: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)

    plan: Mapped[str] = mapped_column(String(40), nullable=False, default="bi_eleitoral_completo")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)

    # Dados do comprador (guardados no checkout p/ provisionar sem depender do
    # payload do Asaas). buyer_name vira nome/slug do tenant.
    billing_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    buyer_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    buyer_cpf_cnpj: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Contexto do produto escolhido no checkout (uf/município do B.I.).
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    municipality: Mapped[str | None] = mapped_column(String(120), nullable=True)

    value: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    cycle: Mapped[str] = mapped_column(String(20), nullable=False, default="MONTHLY")
    # Próximo vencimento (fim do período pago) — atualizado a cada PAYMENT_RECEIVED.
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_payment_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_event_id: Mapped[str | None] = mapped_column(String(80), nullable=True)


class BillingEvent(Base):
    """Idempotência do webhook do Asaas: 1 linha por event id já processado."""

    __tablename__ = "billing_events"

    asaas_event_id: Mapped[str] = mapped_column(
        String(80), nullable=False, unique=True, index=True
    )
    event_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payload: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
