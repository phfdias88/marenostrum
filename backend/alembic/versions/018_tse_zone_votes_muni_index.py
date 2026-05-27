"""tse: índice (municipality_id, votes) p/ top candidatos por zona

Revision ID: 018
Revises: 017
Create Date: 2026-05-27

O endpoint /municipalities/{id}/zones filtra por município; o índice único
lidera por candidate_id, então sem este índice a consulta varria a tabela.
Idempotente (IF NOT EXISTS) — o índice já foi criado em produção via SQL.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tse_zone_votes_muni "
        "ON tse_candidate_zone_votes (municipality_id, votes)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tse_zone_votes_muni")
