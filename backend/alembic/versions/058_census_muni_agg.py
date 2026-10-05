"""census_muni_agg — agregados municipais do censo MATERIALIZADOS

O /census/uf-overview fazia um LEFT JOIN LATERAL que somava ~26k setores
(30+ colunas) POR REQUEST fria — os 3,3s medidos no frio. O dado é estático
entre ingests, então materializamos a agregação numa tabela pequena (1 linha
por município) e o endpoint vira um JOIN plano.

A tabela é preenchida AQUI com exatamente o MESMO SQL de agregação do endpoint
(GROUP BY em vez de LATERAL) — valores idênticos por construção. Após um novo
ingest de censo, rodar scripts/refresh_census_muni_agg.py (mesmo SQL).

Revision ID: 058
Revises: 057
"""
from typing import Sequence, Union

from alembic import op

revision: str = "058"
down_revision: Union[str, None] = "057"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Fonte única do SQL de agregação (migration e refresh usam o mesmo texto —
# scripts/refresh_census_muni_agg.py importa daqui se rodado via PYTHONPATH,
# senão copia literal).
AGG_SELECT = (
    "SELECT s.cd_mun, "
    "       count(*) AS setores, "
    "       round(100*sum(alfabetizados_15mais)::numeric"
    "             / NULLIF(sum(pop_15mais),0), 1) AS taxa_alfabetizacao, "
    "       round(100*(coalesce(sum(raca_preta),0)+coalesce(sum(raca_parda),0))::numeric"
    "             / NULLIF(sum(populacao),0), 1) AS pct_pretos_pardos, "
    "       round(100*coalesce(sum(raca_branca),0)::numeric/NULLIF(sum(populacao),0),1) AS pct_branca, "
    "       round(100*coalesce(sum(raca_preta),0)::numeric/NULLIF(sum(populacao),0),1) AS pct_preta, "
    "       round(100*coalesce(sum(raca_parda),0)::numeric/NULLIF(sum(populacao),0),1) AS pct_parda, "
    "       round(100*coalesce(sum(raca_amarela),0)::numeric/NULLIF(sum(populacao),0),1) AS pct_amarela, "
    "       round(100*coalesce(sum(raca_indigena),0)::numeric/NULLIF(sum(populacao),0),1) AS pct_indigena, "
    "       round(100*sum(populacao) FILTER (WHERE situacao='Urbana')::numeric"
    "             / NULLIF(sum(populacao),0), 1) AS pct_urbana, "
    "       sum(sexo_masculino) AS sexo_masculino, sum(sexo_feminino) AS sexo_feminino, "
    "       sum(idade_0_4) AS idade_0_4, sum(idade_5_9) AS idade_5_9, "
    "       sum(idade_10_14) AS idade_10_14, sum(idade_15_19) AS idade_15_19, "
    "       sum(idade_20_24) AS idade_20_24, sum(idade_25_29) AS idade_25_29, "
    "       sum(idade_30_39) AS idade_30_39, sum(idade_40_49) AS idade_40_49, "
    "       sum(idade_50_59) AS idade_50_59, sum(idade_60_69) AS idade_60_69, "
    "       sum(idade_70_mais) AS idade_70_mais "
    "FROM census_geo s WHERE s.level='setor' GROUP BY s.cd_mun"
)


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS census_muni_agg ("
        "  cd_mun text PRIMARY KEY,"
        "  setores integer,"
        "  taxa_alfabetizacao numeric,"
        "  pct_pretos_pardos numeric,"
        "  pct_branca numeric, pct_preta numeric, pct_parda numeric,"
        "  pct_amarela numeric, pct_indigena numeric,"
        "  pct_urbana numeric,"
        "  sexo_masculino bigint, sexo_feminino bigint,"
        "  idade_0_4 bigint, idade_5_9 bigint, idade_10_14 bigint,"
        "  idade_15_19 bigint, idade_20_24 bigint, idade_25_29 bigint,"
        "  idade_30_39 bigint, idade_40_49 bigint, idade_50_59 bigint,"
        "  idade_60_69 bigint, idade_70_mais bigint"
        ")"
    )
    # População inicial: um único passe nos ~205k setores (segundos), em vez
    # de por-request. Idempotente (TRUNCATE + INSERT).
    op.execute("TRUNCATE census_muni_agg")
    op.execute(f"INSERT INTO census_muni_agg {AGG_SELECT}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS census_muni_agg")
