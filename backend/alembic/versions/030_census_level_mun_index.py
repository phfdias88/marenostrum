"""índice composto census_geo(level, cd_mun) — acelera uf-overview e /setores

Revision ID: 030
Revises: 029
Create Date: 2026-06-10

O uf-overview conta setores por município (subquery com level+cd_mun) e o
/setores filtra level+cd_mun. O índice antigo (só cd_mun) obrigava filter
extra por level em cada lookup.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_census_geo_level_mun "
        "ON census_geo (level, cd_mun)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_census_geo_level_mun")
