"""ia: cache de relatórios estratégicos por candidato

Revision ID: 024
Revises: 023
Create Date: 2026-06-02

Gap EleitoAI fase 3: relatório estratégico gerado por IA (Gemini).
Cache GLOBAL por candidato (dado público, mesmo pra todos os tenants) —
gera uma vez, serve sempre. Economiza cota da API de IA.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS ai_reports ("
        "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
        "  candidate_id uuid NOT NULL UNIQUE,"
        "  content jsonb NOT NULL,"
        "  model varchar(40) NULL,"
        "  created_at timestamptz NOT NULL DEFAULT now()"
        ")"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ai_reports")
