"""tse: indice trigram (pg_trgm) pra busca ILIKE rapida em candidatos

Revision ID: 011
Revises: 010
Create Date: 2026-05-20

Sem isso, /candidates?search= faz seq scan em 454k linhas (~0.5s).
Com GIN trigram, ILIKE '%termo%' usa indice (~50ms).
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
        "CREATE INDEX IF NOT EXISTS ix_tse_candidates_name_trgm "
        "ON tse_candidates USING gin (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tse_candidates_urn_trgm "
        "ON tse_candidates USING gin (urn_name gin_trgm_ops)"
    )
    # Municipios tambem (busca por nome de cidade)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tse_municipalities_name_trgm "
        "ON tse_municipalities USING gin (name gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tse_municipalities_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_tse_candidates_urn_trgm")
    op.execute("DROP INDEX IF EXISTS ix_tse_candidates_name_trgm")
