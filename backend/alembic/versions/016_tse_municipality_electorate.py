"""tse: perfil do eleitorado por município (gênero/idade/escolaridade)

Revision ID: 016
Revises: 015
Create Date: 2026-05-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tse_municipality_electorate",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("municipality_id", sa.UUID(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("total", sa.BigInteger(), nullable=False),
        sa.Column("by_gender", sa.JSON(), nullable=False),
        sa.Column("by_age", sa.JSON(), nullable=False),
        sa.Column("by_education", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["municipality_id"], ["tse_municipalities.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tse_muni_electorate_unique",
        "tse_municipality_electorate",
        ["municipality_id", "year"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_tse_muni_electorate_unique", table_name="tse_municipality_electorate")
    op.drop_table("tse_municipality_electorate")
