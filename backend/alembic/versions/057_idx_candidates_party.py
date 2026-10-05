"""índice em tse_candidates.party_id — party_evolution fazia seq scan de 1,5M linhas

O endpoint de evolução do partido filtra candidatos por party_id, única FK da
tabela SEM índice — cada request fria varria a tabela inteira. Writes em
tse_candidates só acontecem em imports (raros), então o custo do índice é
desprezível.

Revision ID: 057
Revises: 056
"""
from typing import Sequence, Union

from alembic import op

revision: str = "057"
down_revision: Union[str, None] = "056"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS (idempotente, padrão do projeto). CREATE INDEX normal (não
    # CONCURRENTLY): roda em segundos e a tabela só recebe writes em imports.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tse_candidates_party_id "
        "ON tse_candidates (party_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tse_candidates_party_id")
