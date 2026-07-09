"""Índice na expressão de match da trajetória (regressão de performance).

O fix do bug "André das Clínicas" trocou o match de pessoa para
    coalesce(name_unaccent, lower(f_unaccent(name)))
— expressão que NÃO casa com nenhum índice existente (a 025 indexou
lower(f_unaccent(name)); o GIN trgm é em name_unaccent). Resultado: o
/candidates/{id}/trajectory — disparado em TODO load de página de candidato —
voltou ao seq scan de milhões de linhas. Este índice usa a expressão EXATA da
query, devolvendo o index scan (e viabilizando BitmapOr com o índice de cpf).

IF NOT EXISTS: em produção o índice pode ser criado ANTES do deploy via
CREATE INDEX CONCURRENTLY manual (evita segurar o boot no ALTER — o entrypoint
roda alembic no start); aí este upgrade vira no-op.

Revision ID: 053
Revises: 052
"""
from typing import Sequence, Union

from alembic import op

revision: str = "053"
down_revision: Union[str, None] = "052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS ix_tse_candidates_name_norm "
    "ON tse_candidates "
    "(coalesce(name_unaccent, lower(f_unaccent(name))))"
)


def upgrade() -> None:
    op.execute(_INDEX_SQL)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tse_candidates_name_norm")
