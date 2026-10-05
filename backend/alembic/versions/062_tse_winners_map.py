"""tse_winners_map: vencedor por municipio, materializado

Revision ID: 062
Revises: 061
Create Date: 2026-08-17

POR QUE: /stats/winners-map calculava o vencedor na hora, com DISTINCT ON sobre
o cruzamento votos x candidatos. Para Deputado Federal 2022 isso significa
ordenar 3,3 MILHOES de linhas para devolver 5.570 — medido em 164s pela API,
com 85MB de arquivo temporario em disco e 124s so de espera de I/O. Na pratica
o usuario desistia antes.

O resultado e imutavel entre importacoes do TSE, entao vira tabela: sao no
maximo 234 mil linhas (42 combinacoes ano x cargo x 5.570 municipios), contra
os 23,8 milhoes de tse_vote_results que a consulta varria.

Popular/atualizar com scripts/refresh_tse_winners_map.py (roda depois de cada
import do TSE — mesmo padrao do census_muni_agg da migration 058).
"""
from typing import Sequence, Union

from alembic import op


revision: str = "062"
down_revision: Union[str, None] = "061"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS tse_winners_map (
            year            integer      NOT NULL,
            office_code     integer      NOT NULL,
            municipality_id uuid         NOT NULL,
            candidate_id    uuid         NOT NULL,
            urn_name        varchar(120),
            party_abbr      varchar(20),
            party_number    integer,
            votes           integer      NOT NULL,
            latitude        double precision,
            longitude       double precision,
            municipality    varchar(120),
            state           varchar(2),
            updated_at      timestamptz  NOT NULL DEFAULT now(),
            PRIMARY KEY (year, office_code, municipality_id)
        )
    """)
    # A PK (year, office_code, municipality_id) ja atende a consulta do mapa,
    # que sempre filtra ano+cargo e devolve todos os municipios em ordem.
    op.execute(
        "COMMENT ON TABLE tse_winners_map IS "
        "'Vencedor por municipio (ano+cargo). Materializado — atualizar com "
        "scripts/refresh_tse_winners_map.py apos import do TSE.'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tse_winners_map")
