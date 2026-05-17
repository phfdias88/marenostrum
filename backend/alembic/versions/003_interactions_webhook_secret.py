"""interactions + tenants.webhook_secret

Revision ID: 003
Revises: 002
Create Date: 2026-05-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tenants ganha coluna webhook_secret (nullable — tenant pode ainda nao
    # ter integracao configurada). Definir por seed/admin endpoint futuro.
    op.add_column(
        "tenants",
        sa.Column("webhook_secret", sa.String(128), nullable=True),
    )

    # Interactions: registro imutavel de eventos externos vinculados ao CRM
    op.create_table(
        "interactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        # FK opcional: contato pode nao existir (interacao orfa)
        sa.Column(
            "contact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("event_type", sa.String(80), nullable=True),
        sa.Column(
            "channel",
            sa.String(40),
            nullable=False,
            server_default="whatsapp",
        ),
        sa.Column("external_event_id", sa.String(120), nullable=True),
        # JSON cross-DB. Em PG resolve pra json (nao JSONB — migrar depois
        # se precisar de operadores e indices GIN).
        sa.Column("payload_data", sa.JSON(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # Indices: todas as queries comecam filtrando por tenant_id
    op.create_index("ix_interactions_tenant_id", "interactions", ["tenant_id"])
    op.create_index(
        "ix_interactions_tenant_id_id", "interactions", ["tenant_id", "id"]
    )
    op.create_index(
        "ix_interactions_tenant_contact",
        "interactions",
        ["tenant_id", "contact_id"],
    )
    op.create_index(
        "ix_interactions_tenant_phone",
        "interactions",
        ["tenant_id", "phone"],
    )
    op.create_index(
        "ix_interactions_tenant_received_at",
        "interactions",
        ["tenant_id", "received_at"],
    )
    op.create_index(
        "ix_interactions_external_event_id",
        "interactions",
        ["external_event_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_interactions_external_event_id", table_name="interactions")
    op.drop_index("ix_interactions_tenant_received_at", table_name="interactions")
    op.drop_index("ix_interactions_tenant_phone", table_name="interactions")
    op.drop_index("ix_interactions_tenant_contact", table_name="interactions")
    op.drop_index("ix_interactions_tenant_id_id", table_name="interactions")
    op.drop_index("ix_interactions_tenant_id", table_name="interactions")
    op.drop_table("interactions")
    op.drop_column("tenants", "webhook_secret")
