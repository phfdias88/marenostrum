"""ai_census_insights — leitura estratégica da Maré IA por município (censo)

Revision ID: 031
Revises: 030
Create Date: 2026-06-10
"""
from typing import Sequence, Union

from alembic import op


revision: str = "031"
down_revision: Union[str, None] = "030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS ai_census_insights ("
        "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
        "  cd_mun varchar(7) NOT NULL,"
        "  content jsonb NOT NULL,"
        "  model varchar(60) NOT NULL,"
        "  created_at timestamptz NOT NULL DEFAULT now(),"
        "  CONSTRAINT uq_ai_census_mun UNIQUE (cd_mun)"
        ")"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ai_census_insights")
