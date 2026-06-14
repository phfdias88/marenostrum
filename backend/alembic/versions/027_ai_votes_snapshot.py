"""ia: snapshot de votos pra invalidar cache quando dados mudam

Revision ID: 027
Revises: 026
Create Date: 2026-06-05

Adiciona votes_snapshot às tabelas de cache de IA. Ao gerar um relatório/
confronto, guardamos a votação total usada. Na leitura, se a votação atual
diferir do snapshot (ex: re-sync do TSE corrigiu os votos), o cache é
considerado obsoleto e o relatório é regenerado — garantindo que a Maré IA
sempre reflita os dados vigentes.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE ai_reports ADD COLUMN IF NOT EXISTS votes_snapshot bigint")
    op.execute("ALTER TABLE ai_comparisons ADD COLUMN IF NOT EXISTS votes_snapshot bigint")


def downgrade() -> None:
    op.execute("ALTER TABLE ai_reports DROP COLUMN IF EXISTS votes_snapshot")
    op.execute("ALTER TABLE ai_comparisons DROP COLUMN IF EXISTS votes_snapshot")
