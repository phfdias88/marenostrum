"""contacts.is_active (soft delete) + tabela demands

Revision ID: 004
Revises: 003
Create Date: 2026-05-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Soft delete em contacts ----------------------------------------
    # Default no DDL = registros existentes ficam ativos automaticamente.
    op.add_column(
        "contacts",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    # Indice parcial pra acelerar list/search (queries de leitura sempre
    # filtram is_active=true). Especifico de Postgres.
    op.create_index(
        "ix_contacts_tenant_active",
        "contacts",
        ["tenant_id"],
        postgresql_where=sa.text("is_active = true"),
    )

    # --- Enum demand_status ---------------------------------------------
    demand_status = postgresql.ENUM(
        "aberta", "em_andamento", "resolvida", "cancelada",
        name="demand_status", create_type=True,
    )
    demand_status.create(op.get_bind(), checkfirst=True)

    # --- Tabela demands -------------------------------------------------
    op.create_table(
        "demands",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "contact_id",
            postgresql.UUID(as_uuid=True),
            # RESTRICT: protege contra hard-delete administrativo de contato
            # que ainda tem demanda associada.
            sa.ForeignKey("contacts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="demand_status", create_type=False),
            nullable=False,
        ),
        sa.Column("category", sa.String(80), nullable=False),
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
    op.create_index("ix_demands_tenant_id", "demands", ["tenant_id"])
    op.create_index("ix_demands_tenant_id_id", "demands", ["tenant_id", "id"])
    op.create_index(
        "ix_demands_tenant_contact", "demands", ["tenant_id", "contact_id"]
    )
    op.create_index(
        "ix_demands_tenant_status", "demands", ["tenant_id", "status"]
    )
    op.create_index(
        "ix_demands_tenant_created_at", "demands", ["tenant_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_demands_tenant_created_at", table_name="demands")
    op.drop_index("ix_demands_tenant_status", table_name="demands")
    op.drop_index("ix_demands_tenant_contact", table_name="demands")
    op.drop_index("ix_demands_tenant_id_id", table_name="demands")
    op.drop_index("ix_demands_tenant_id", table_name="demands")
    op.drop_table("demands")
    sa.Enum(name="demand_status").drop(op.get_bind(), checkfirst=True)
    op.drop_index("ix_contacts_tenant_active", table_name="contacts")
    op.drop_column("contacts", "is_active")
