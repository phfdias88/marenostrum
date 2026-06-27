"""tse: filiação partidária por partido × município (perfil_filiacao_partidaria)

Revision ID: 044
Revises: 043
Create Date: 2026-06-27

Tabela GLOBAL (dado público TSE, sem tenant_id) — 1 linha por
(partido, município, período AAAAMM) com total + breakdowns demográficos JSON.
Espelha tse_municipality_electorate.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "044"
down_revision: Union[str, None] = "043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tse_party_membership",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("party_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tse_parties.id", ondelete="CASCADE"), nullable=False),
        sa.Column("municipality_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tse_municipalities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period", sa.Integer(), nullable=False),
        sa.Column("total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("by_gender", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("by_age", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("by_education", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_tse_party_membership_unique", "tse_party_membership",
                    ["party_id", "municipality_id", "period"], unique=True)
    op.create_index("ix_tse_party_membership_party", "tse_party_membership",
                    ["party_id", "period"])
    op.create_index("ix_tse_party_membership_muni", "tse_party_membership",
                    ["municipality_id", "period"])


def downgrade() -> None:
    op.drop_table("tse_party_membership")
