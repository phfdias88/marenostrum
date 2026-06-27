"""tse: CPF do candidato (ID único da pessoa) — agrupar candidaturas

Revision ID: 041
Revises: 040
Create Date: 2026-06-27

CPF identifica a PESSOA de forma única entre eleições/cargos/UFs — resolve a
unificação da busca (Bolsonaro, Dilma president+senadora, etc.) onde nome+UF
falhava. Populado do dataset consulta_cand do TSE (por SQ_CANDIDATO). Nullable:
candidaturas sem consulta_cand importado caem no fallback nome+UF.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "041"
down_revision: Union[str, None] = "040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE tse_candidates ADD COLUMN IF NOT EXISTS cpf varchar(11) NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tse_candidates_cpf ON tse_candidates (cpf)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tse_candidates_cpf")
    op.execute("ALTER TABLE tse_candidates DROP COLUMN IF EXISTS cpf")
