"""census_geo — renda dos responsáveis em domicílios particulares permanentes
ocupados (Censo 2022). Fonte: IBGE, Agregados por Setores Censitários —
Rendimento do Responsável (V06004 média, V06006 mediana), nível município.

Colunas NOVAS (não sobrescreve a renda domiciliar de 2010, que é outro conceito):
  renda_media_resp_2022, renda_mediana_resp_2022 (R$ nominais de 2022).

Revision ID: 051
Revises: 050
"""
from typing import Sequence, Union

from alembic import op

revision: str = "051"
down_revision: Union[str, None] = "050"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE census_geo ADD COLUMN IF NOT EXISTS renda_media_resp_2022 double precision"
    )
    op.execute(
        "ALTER TABLE census_geo ADD COLUMN IF NOT EXISTS renda_mediana_resp_2022 double precision"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE census_geo DROP COLUMN IF EXISTS renda_mediana_resp_2022")
    op.execute("ALTER TABLE census_geo DROP COLUMN IF EXISTS renda_media_resp_2022")
