"""Local de votacao passa a carregar a ZONA na identidade.

No TSE o NR_LOCAL_VOTACAO so e unico DENTRO da zona eleitoral. A chave antiga
(ano, municipio, local) fundia locais distintos de zonas diferentes numa linha
so: os votos somavam certo no total do municipio, mas o bairro de um dos locais
levava os votos de todos.

Medido em producao antes do conserto: Rio de Janeiro com 163 locais (a cidade
tem mais de 1.400), somando 5.009.373 eleitores — correto no total — com um
unico "local" de 129.241 eleitores.

Esta migration so prepara o esquema. Os dados so ficam certos DEPOIS de
reimportar locais e secoes com a zona; ate la `zone` fica nulo nas linhas
antigas e a quebra por bairro segue aproximada.

Revision ID: 064
Revises: 063
"""
from alembic import op
import sqlalchemy as sa

revision = "064"
down_revision = "063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tse_voting_places",
        sa.Column("zone", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_tse_voting_places_zone", "tse_voting_places", ["zone"],
    )

    # A chave nova precisa existir antes de a antiga sair, senao abre uma
    # janela sem protecao nenhuma contra duplicata.
    op.execute(
        "CREATE UNIQUE INDEX ix_tse_voting_places_year_muni_zone_code "
        "ON tse_voting_places (year, municipality_id, zone, local_code) "
        "NULLS NOT DISTINCT"
    )
    op.drop_index("ix_tse_voting_places_year_muni_code", "tse_voting_places")


def downgrade() -> None:
    op.create_index(
        "ix_tse_voting_places_year_muni_code", "tse_voting_places",
        ["year", "municipality_id", "local_code"], unique=True,
    )
    op.drop_index("ix_tse_voting_places_year_muni_zone_code", "tse_voting_places")
    op.drop_index("ix_tse_voting_places_zone", "tse_voting_places")
    op.drop_column("tse_voting_places", "zone")
