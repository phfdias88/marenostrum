"""electorate: estado civil + raça/cor por município (TSE perfil_eleitorado)

Revision ID: 043
Revises: 042
Create Date: 2026-06-27

DS_ESTADO_CIVIL e DS_RACA_COR já vêm no perfil_eleitorado_<ano>.csv mas não eram
capturados. Colunas JSON nullable (linhas antigas ficam sem; re-importar o
perfil popula). Mesmo padrão de by_gender/by_age/by_education.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "043"
down_revision: Union[str, None] = "042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLS = ["by_marital_status", "by_race"]


def upgrade() -> None:
    for c in COLS:
        op.execute(
            f"ALTER TABLE tse_municipality_electorate ADD COLUMN IF NOT EXISTS {c} jsonb"
        )


def downgrade() -> None:
    for c in COLS:
        op.execute(f"ALTER TABLE tse_municipality_electorate DROP COLUMN IF EXISTS {c}")
