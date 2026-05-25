"""tse: enriquecimento do candidato (patrimonio + redes sociais)

Revision ID: 012
Revises: 011
Create Date: 2026-05-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tse_candidates",
        sa.Column("assets_total", sa.Float(), nullable=True),
    )
    op.add_column(
        "tse_candidates",
        sa.Column("social_links", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tse_candidates", "social_links")
    op.drop_column("tse_candidates", "assets_total")
