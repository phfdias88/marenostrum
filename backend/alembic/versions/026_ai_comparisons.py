"""ia: cache de confrontos estratégicos (candidato × adversário)

Revision ID: 026
Revises: 025
Create Date: 2026-06-05

Maré IA comparativa: relatório de confronto direto entre dois candidatos,
gerado por IA. Cache direcional por par (candidate_id, adversary_id) — o
relatório é sempre da perspectiva do `candidate_id`.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "026"
down_revision: Union[str, None] = "025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS ai_comparisons ("
        "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
        "  candidate_id uuid NOT NULL,"
        "  adversary_id uuid NOT NULL,"
        "  content jsonb NOT NULL,"
        "  model varchar(40) NULL,"
        "  created_at timestamptz NOT NULL DEFAULT now(),"
        "  CONSTRAINT uq_ai_comparisons_pair UNIQUE (candidate_id, adversary_id)"
        ")"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ai_comparisons")
