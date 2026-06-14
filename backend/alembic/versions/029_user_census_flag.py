"""users.census_enabled — feature-flag do módulo Censo por usuário

Revision ID: 029
Revises: 028
Create Date: 2026-06-09

O owner libera/bloqueia o módulo de Dados Censitários (IBGE) por usuário.
Default false — ninguém vê até o admin liberar.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("census_enabled", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "census_enabled")
