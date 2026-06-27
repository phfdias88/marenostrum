"""census_geo: renda domiciliar por município (IBGE Censo 2022, SIDRA t/3168)

Revision ID: 042
Revises: 041
Create Date: 2026-06-27

Renda nominal média e mediana mensal dos domicílios particulares permanentes,
nível MUNICÍPIO (a única granularidade que o IBGE publica de forma estável p/
renda — o agregado por setor não traz renda). Populado da API SIDRA
(apisidra.ibge.gov.br, tabela 3168, variáveis 847=média e 848=mediana).
Só as linhas level='municipio' recebem valor; setor fica NULL.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "042"
down_revision: Union[str, None] = "041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLS = ["renda_media_domiciliar", "renda_mediana_domiciliar"]


def upgrade() -> None:
    for c in COLS:
        op.execute(f"ALTER TABLE census_geo ADD COLUMN IF NOT EXISTS {c} double precision")


def downgrade() -> None:
    for c in COLS:
        op.execute(f"ALTER TABLE census_geo DROP COLUMN IF EXISTS {c}")
