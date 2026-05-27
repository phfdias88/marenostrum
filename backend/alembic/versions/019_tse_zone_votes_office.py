"""tse: office_code denormalizado na tabela de votos-zona

Revision ID: 019
Revises: 018
Create Date: 2026-05-27

Evita JOIN pesado ao filtrar cargo no "top candidatos por zona" de cidades
grandes (era ~3,2s cold). Backfill + índice. Idempotente — já aplicado em
produção via SQL.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE tse_candidate_zone_votes ADD COLUMN IF NOT EXISTS office_code integer")
    op.execute(
        "UPDATE tse_candidate_zone_votes z SET office_code = c.office_code "
        "FROM tse_candidates c WHERE c.id = z.candidate_id AND z.office_code IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tse_zone_votes_muni_office "
        "ON tse_candidate_zone_votes (municipality_id, office_code, votes)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tse_zone_votes_muni_office")
    op.execute("ALTER TABLE tse_candidate_zone_votes DROP COLUMN IF EXISTS office_code")
