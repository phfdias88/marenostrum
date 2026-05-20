"""tse: pg_trgm + GIN indexes pra acelerar busca ILIKE

Revision ID: 011
Revises: 010
Create Date: 2026-05-20
"""
from typing import Sequence, Union

from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tse_candidates_urn_trgm "
        "ON tse_candidates USING gin (urn_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tse_candidates_name_trgm "
        "ON tse_candidates USING gin (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tse_municipalities_name_trgm "
        "ON tse_municipalities USING gin (name gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tse_municipalities_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_tse_candidates_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_tse_candidates_urn_trgm")
