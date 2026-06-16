"""contacts: voting_place (local de votação)

Revision ID: 034
Revises: 033
Create Date: 2026-06-16

Onde o contato vota — nome do local da base TSE. Nullable.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "034"
down_revision: Union[str, None] = "033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "contacts", sa.Column("voting_place", sa.String(length=200), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("contacts", "voting_place")
