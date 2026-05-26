"""tse: financas de campanha (receita/despesa total) no candidato

Revision ID: 014
Revises: 013
Create Date: 2026-05-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tse_candidates", sa.Column("revenue_total", sa.Float(), nullable=True))
    op.add_column("tse_candidates", sa.Column("expense_total", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("tse_candidates", "expense_total")
    op.drop_column("tse_candidates", "revenue_total")
