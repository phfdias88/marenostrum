"""tse_candidates: name_unaccent/urn_unaccent materializados + trigger

A busca fazia f_unaccent(name) ILIKE ... e o recheck do índice GIN trgm
recomputava unaccent por linha — ~16s pra "silva" (86k matches). Materializamos
o nome sem acento em colunas mantidas por trigger; o índice GIN trgm vai nas
colunas (criado pelo scripts/backfill_candidate_unaccent.py, CONCURRENTLY).

Esta migration só faz o DDL rápido (colunas + trigger). O backfill dos valores
existentes e os índices GIN rodam no script (pesados, fora do alembic).

Revision ID: 048
Revises: 047
"""
from typing import Sequence, Union

from alembic import op

revision: str = "048"
down_revision: Union[str, None] = "047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE tse_candidates ADD COLUMN IF NOT EXISTS name_unaccent varchar(180)")
    op.execute("ALTER TABLE tse_candidates ADD COLUMN IF NOT EXISTS urn_unaccent varchar(180)")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION tse_cand_unaccent_trg() RETURNS trigger AS $$
        BEGIN
            NEW.name_unaccent := lower(public.f_unaccent(NEW.name));
            NEW.urn_unaccent := lower(public.f_unaccent(NEW.urn_name));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_tse_cand_unaccent ON tse_candidates")
    op.execute(
        """
        CREATE TRIGGER trg_tse_cand_unaccent
        BEFORE INSERT OR UPDATE OF name, urn_name ON tse_candidates
        FOR EACH ROW EXECUTE FUNCTION tse_cand_unaccent_trg();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_tse_cand_unaccent ON tse_candidates")
    op.execute("DROP FUNCTION IF EXISTS tse_cand_unaccent_trg()")
    op.execute("ALTER TABLE tse_candidates DROP COLUMN IF EXISTS name_unaccent")
    op.execute("ALTER TABLE tse_candidates DROP COLUMN IF EXISTS urn_unaccent")
