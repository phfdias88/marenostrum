"""perf: índice funcional p/ trajetória (match por nome civil normalizado)

Revision ID: 025
Revises: 024
Create Date: 2026-06-05

A trajetória do candidato e o _gather_facts do relatório IA casam candidatos
da MESMA pessoa por `lower(f_unaccent(name))` sobre ~1.46M linhas. Sem índice
nessa expressão, era seq scan (~12s). Com o índice B-tree funcional, a busca
de igualdade fica instantânea (~0.15s). f_unaccent é IMMUTABLE (migração 015),
então pode ser indexada.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS: o índice já pode ter sido criado CONCURRENTLY em produção.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tse_candidates_name_norm "
        "ON tse_candidates (lower(public.f_unaccent(name)))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tse_candidates_name_norm")
