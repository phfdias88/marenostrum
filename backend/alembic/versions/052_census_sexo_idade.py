"""census_geo — sexo e faixa etária (Censo 2022, agregado Demografia por setor).

Sexo:  V01007 (masculino), V01008 (feminino).
Faixa etária (totais ambos os sexos): V01031..V01041 — 11 faixas de 5 anos
(0-4, 5-9, ..., 60-69, 70+). Contagens por setor; agregam pra município via SUM.

Revision ID: 052
Revises: 051
"""
from typing import Sequence, Union

from alembic import op

revision: str = "052"
down_revision: Union[str, None] = "051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLS = [
    "sexo_masculino", "sexo_feminino",
    "idade_0_4", "idade_5_9", "idade_10_14", "idade_15_19", "idade_20_24",
    "idade_25_29", "idade_30_39", "idade_40_49", "idade_50_59", "idade_60_69",
    "idade_70_mais",
]


def upgrade() -> None:
    for c in _COLS:
        op.execute(f"ALTER TABLE census_geo ADD COLUMN IF NOT EXISTS {c} integer")


def downgrade() -> None:
    for c in reversed(_COLS):
        op.execute(f"ALTER TABLE census_geo DROP COLUMN IF EXISTS {c}")
