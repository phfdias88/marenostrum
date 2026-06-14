"""census_geo: alfabetização (15+) e cor/raça por setor (IBGE Censo 2022)

Revision ID: 032
Revises: 031
Create Date: 2026-06-10

Variáveis conforme o dicionário oficial dos Agregados por Setores:
- alfabetizados_15mais = soma V00644..V00656 (arquivo alfabetizacao)
- pop_15mais = V01006 − (V01009..V01011 + V01020..V01022) (arquivo demografia)
- raca_* = V01317..V01321 (arquivo cor_ou_raca)
"""
from typing import Sequence, Union

from alembic import op


revision: str = "032"
down_revision: Union[str, None] = "031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLS = [
    "alfabetizados_15mais", "pop_15mais",
    "raca_branca", "raca_preta", "raca_amarela", "raca_parda", "raca_indigena",
]


def upgrade() -> None:
    for c in COLS:
        op.execute(f"ALTER TABLE census_geo ADD COLUMN IF NOT EXISTS {c} integer")


def downgrade() -> None:
    for c in COLS:
        op.execute(f"ALTER TABLE census_geo DROP COLUMN IF EXISTS {c}")
