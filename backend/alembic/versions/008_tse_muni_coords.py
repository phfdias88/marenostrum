"""tse: lat/lng nos municipios (populado via dataset publico)

Revision ID: 008
Revises: 007
Create Date: 2026-05-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tse_municipalities",
        sa.Column("latitude", sa.Float(), nullable=True),
    )
    op.add_column(
        "tse_municipalities",
        sa.Column("longitude", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tse_municipalities", "longitude")
    op.drop_column("tse_municipalities", "latitude")
