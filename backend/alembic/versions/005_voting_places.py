"""voting_places: locais de votacao + votos agregados

Revision ID: 005
Revises: 004
Create Date: 2026-05-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "voting_places",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("address", sa.String(255), nullable=True),
        sa.Column("neighborhood", sa.String(100), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(2), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("votes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_voters", sa.Integer(), nullable=True),
        sa.Column("election_year", sa.Integer(), nullable=True),
        sa.Column("tse_code", sa.String(40), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
    op.create_index("ix_voting_places_tenant_id", "voting_places", ["tenant_id"])
    op.create_index(
        "ix_voting_places_tenant_id_id", "voting_places", ["tenant_id", "id"]
    )
    op.create_index(
        "ix_voting_places_tenant_year",
        "voting_places",
        ["tenant_id", "election_year"],
    )
    op.create_index(
        "ix_voting_places_tenant_geo",
        "voting_places",
        ["tenant_id", "latitude", "longitude"],
    )


def downgrade() -> None:
    op.drop_index("ix_voting_places_tenant_geo", table_name="voting_places")
    op.drop_index("ix_voting_places_tenant_year", table_name="voting_places")
    op.drop_index("ix_voting_places_tenant_id_id", table_name="voting_places")
    op.drop_index("ix_voting_places_tenant_id", table_name="voting_places")
    op.drop_table("voting_places")
