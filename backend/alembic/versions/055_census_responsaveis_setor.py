"""census_geo — nº de responsáveis por setor (peso da média ponderada de renda).

O Censo 2022 publicou o "Rendimento médio dos responsáveis" por SETOR
(ingest_census_renda_setor.py). Pra estimar a renda de um BAIRRO/DISTRITO,
a média dos setores é ponderada pelo nº de responsáveis (V06001) — daí esta
coluna. renda_media_resp_2022/renda_mediana_resp_2022 já existem (migration 051,
table-wide); aqui falta só o peso.

CRÍTICO: sem esta coluna o /census/setores (que faz SELECT ... responsaveis_2022)
quebra em produção — o pytest não pega porque census_geo é SQL cru (fora do
create_all do harness SQLite).

Revision ID: 055
Revises: 054
"""
from typing import Sequence, Union

from alembic import op

revision: str = "055"
down_revision: Union[str, None] = "054"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE census_geo ADD COLUMN IF NOT EXISTS responsaveis_2022 integer"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE census_geo DROP COLUMN IF EXISTS responsaveis_2022")
