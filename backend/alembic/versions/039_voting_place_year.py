"""tse: dimensão de ano nos locais de votação (suporta 2020/2022 além de 2024)

Revision ID: 039
Revises: 038
Create Date: 2026-06-27

tse_voting_places só guardava UM ano (2024) — dedup por (municipality_id,
local_code). Pra importar voto-por-bairro de outros anos (2020 municipal,
2022 federal/estadual) sem colidir, adiciona `year` e troca o unique pra
(year, municipality_id, local_code). Linhas existentes viram 2024.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "039"
down_revision: Union[str, None] = "038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tse_voting_places "
        "ADD COLUMN IF NOT EXISTS year integer NOT NULL DEFAULT 2024"
    )
    # Troca o unique (municipality_id, local_code) -> (year, municipality_id, local_code)
    op.execute("DROP INDEX IF EXISTS ix_tse_voting_places_muni_code")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_tse_voting_places_year_muni_code "
        "ON tse_voting_places (year, municipality_id, local_code)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tse_voting_places_year_muni_code")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_tse_voting_places_muni_code "
        "ON tse_voting_places (municipality_id, local_code)"
    )
    op.execute("ALTER TABLE tse_voting_places DROP COLUMN IF EXISTS year")
