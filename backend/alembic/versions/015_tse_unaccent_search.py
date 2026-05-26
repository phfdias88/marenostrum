"""tse: busca acento-insensível (unaccent + GIN trigram funcional)

Revision ID: 015
Revises: 014
Create Date: 2026-05-26

Sem isso, /candidates?search=evandro%20leitao e /municipalities?search=sao%20luis
voltam vazio (a busca era sensível a acentos). Criamos:
- extensão unaccent
- f_unaccent(text): wrapper IMMUTABLE (unaccent é só STABLE) — necessário
  pra poder indexar a expressão
- indexes GIN trigram em f_unaccent(coluna) → ILIKE acento-insensível rápido

Tudo idempotente (IF NOT EXISTS / OR REPLACE).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE OR REPLACE FUNCTION public.f_unaccent(text) "
        "RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT AS "
        "$$ SELECT public.unaccent('public.unaccent', $1) $$"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tse_candidates_urn_unaccent_trgm "
        "ON tse_candidates USING gin (public.f_unaccent(urn_name) gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tse_candidates_name_unaccent_trgm "
        "ON tse_candidates USING gin (public.f_unaccent(name) gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tse_municipalities_name_unaccent_trgm "
        "ON tse_municipalities USING gin (public.f_unaccent(name) gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tse_municipalities_name_unaccent_trgm")
    op.execute("DROP INDEX IF EXISTS ix_tse_candidates_name_unaccent_trgm")
    op.execute("DROP INDEX IF EXISTS ix_tse_candidates_urn_unaccent_trgm")
    op.execute("DROP FUNCTION IF EXISTS public.f_unaccent(text)")
