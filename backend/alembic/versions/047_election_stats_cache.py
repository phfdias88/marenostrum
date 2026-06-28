"""tse_elections: sumário pré-computado (candidatos, votos, municípios)

Revision ID: 047
Revises: 046
Create Date: 2026-06-28

O endpoint /elections/{id}/stats fazia count(distinct municipio) varrendo
vote_results (5GB+) → 72s em eleições municipais grandes (505k candidatos),
estourando o timeout do nginx na 1ª request (o cache em memória se perde no
restart). Materializamos o sumário em colunas, populadas por
scripts/populate_election_stats.py. Endpoint passa a ler as colunas (instantâneo).
"""
from typing import Sequence, Union

from alembic import op


revision: str = "047"
down_revision: Union[str, None] = "046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLS = ["stats_candidates", "stats_total_votes", "stats_municipalities"]


def upgrade() -> None:
    op.execute("ALTER TABLE tse_elections ADD COLUMN IF NOT EXISTS stats_candidates integer")
    op.execute("ALTER TABLE tse_elections ADD COLUMN IF NOT EXISTS stats_total_votes bigint")
    op.execute("ALTER TABLE tse_elections ADD COLUMN IF NOT EXISTS stats_municipalities integer")


def downgrade() -> None:
    for c in COLS:
        op.execute(f"ALTER TABLE tse_elections DROP COLUMN IF EXISTS {c}")
