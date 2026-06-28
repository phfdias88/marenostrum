"""census_geo: PIB, IDHM, IDEB e saneamento por município

Revision ID: 046
Revises: 045
Create Date: 2026-06-27

Indicadores socioeconômicos por MUNICÍPIO (level='municipio'), mesmo padrão da
renda (042). Fontes:
- PIB (IBGE PIB-Munic): pib_total (R$), pib_per_capita (R$), ref 2023.
- IDHM (Atlas Brasil/PNUD, Censo 2010 — última versão municipal completa):
  idhm + subíndices educação/longevidade/renda (0..1).
- IDEB (INEP 2023, rede pública): ideb_anos_iniciais, ideb_anos_finais.
- Saneamento (Censo 2022 agregados por setor, somado a município): contagens de
  domicílios — água (rede/total), esgoto (adequado/total), lixo (coletado/total);
  o % é calculado na leitura. 'Adequado': água=rede geral; esgoto=rede+fossa
  ligada à rede; lixo=coletado+caçamba.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "046"
down_revision: Union[str, None] = "045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FLOAT_COLS = [
    "pib_total", "pib_per_capita",
    "idhm", "idhm_educacao", "idhm_longevidade", "idhm_renda",
    "ideb_anos_iniciais", "ideb_anos_finais",
]
INT_COLS = [
    "dom_agua_rede", "dom_agua_total",
    "dom_esgoto_adequado", "dom_esgoto_total",
    "dom_lixo_coletado", "dom_lixo_total",
]


def upgrade() -> None:
    for c in FLOAT_COLS:
        op.execute(f"ALTER TABLE census_geo ADD COLUMN IF NOT EXISTS {c} double precision")
    for c in INT_COLS:
        op.execute(f"ALTER TABLE census_geo ADD COLUMN IF NOT EXISTS {c} integer")


def downgrade() -> None:
    for c in FLOAT_COLS + INT_COLS:
        op.execute(f"ALTER TABLE census_geo DROP COLUMN IF EXISTS {c}")
