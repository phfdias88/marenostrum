"""tse: total_votes pre-computado no candidato (ranking rapido)

Revision ID: 013
Revises: 012
Create Date: 2026-05-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tse_candidates",
        sa.Column("total_votes", sa.BigInteger(), nullable=True),
    )
    # Index pra ranking (order by total_votes desc com filtros)
    op.create_index(
        "ix_tse_candidates_total_votes",
        "tse_candidates", ["total_votes"],
    )


def downgrade() -> None:
    op.drop_index("ix_tse_candidates_total_votes", "tse_candidates")
    op.drop_column("tse_candidates", "total_votes")
