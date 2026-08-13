"""billing recorrente (Asaas): subscriptions + billing_events + status no tenant

Cria a base do billing por assinatura do "B.I. Eleitoral Completo" (R$250/mês),
entregue via nosso SaaS:
- `subscriptions`: 1 linha por assinatura (nasce pending, sem tenant; o webhook
  provisiona o tenant e ativa).
- `billing_events`: idempotência do webhook (event id UNIQUE).
- tenants ganha subscription_status (cache barato do gating; LEGADOS ficam
  'active' pra NÃO bloquear quem foi provisionado via seed) e grace_until.

Revision ID: 056
Revises: 055
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "056"
down_revision: Union[str, None] = "055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------------- subscriptions ----------------------
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # nullable: a assinatura existe ANTES do tenant (webhook provisiona depois)
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("asaas_customer_id", sa.String(40), nullable=True),
        sa.Column("asaas_subscription_id", sa.String(40), nullable=True),
        sa.Column("external_reference", sa.String(120), nullable=True),
        sa.Column("plan", sa.String(40), nullable=False, server_default="bi_eleitoral_completo"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("billing_email", sa.String(254), nullable=True),
        sa.Column("buyer_name", sa.String(150), nullable=True),
        sa.Column("buyer_cpf_cnpj", sa.String(20), nullable=True),
        sa.Column("uf", sa.String(2), nullable=True),
        sa.Column("municipality", sa.String(120), nullable=True),
        sa.Column("value", sa.Numeric(10, 2), nullable=True),
        sa.Column("cycle", sa.String(20), nullable=False, server_default="MONTHLY"),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_payment_id", sa.String(40), nullable=True),
        sa.Column("last_event_id", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("asaas_subscription_id", name="uq_subscriptions_asaas_sub_id"),
    )
    op.create_index("ix_subscriptions_tenant_id", "subscriptions", ["tenant_id"])
    op.create_index("ix_subscriptions_asaas_customer_id", "subscriptions", ["asaas_customer_id"])
    op.create_index("ix_subscriptions_asaas_subscription_id", "subscriptions", ["asaas_subscription_id"])
    op.create_index("ix_subscriptions_external_reference", "subscriptions", ["external_reference"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])

    # ---------------------- billing_events (idempotência) ----------------------
    op.create_table(
        "billing_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("asaas_event_id", sa.String(80), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("asaas_event_id", name="uq_billing_events_event_id"),
    )
    op.create_index("ix_billing_events_asaas_event_id", "billing_events", ["asaas_event_id"])

    # ---------------------- tenants: status de assinatura ----------------------
    # IF NOT EXISTS (idempotente, padrão do projeto). Default 'active' pra que os
    # tenants LEGADOS (provisionados via seed.py) NÃO sejam bloqueados pelo gate.
    op.execute(
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS "
        "subscription_status varchar(20) NOT NULL DEFAULT 'active'"
    )
    op.execute(
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS grace_until timestamptz"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS grace_until")
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS subscription_status")
    op.drop_table("billing_events")
    op.drop_table("subscriptions")
