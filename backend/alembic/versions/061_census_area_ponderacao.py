"""census_geo: area de ponderacao como terceira granularidade

Revision ID: 061
Revises: 060
Create Date: 2026-08-15

Prepara a tabela pra carga nacional e pro nivel "area de ponderacao":

1. cd_apond / nm_apond — nos SETORES, `cd_apond` diz a qual area de ponderacao
   o setor pertence (e o que permite agregar setor -> area). Nas linhas de
   nivel `area_ponderacao`, e o codigo da propria area.

2. geometry passa a aceitar NULL. A carga nacional traz os indicadores dos
   ~452 mil setores por CSV, onde geometria nao existe; ela vem depois, por
   shapefile, so nas UFs em uso. Sem isso seria impossivel carregar o pais
   sem antes baixar ~2 GB de malha. As queries que servem GeoJSON passaram a
   filtrar `geometry IS NOT NULL` no mesmo commit.

3. CHECK em `level` — os tres valores validos. Hoje a coluna aceita qualquer
   string; um typo num script de carga ("municipios") criaria linhas invisiveis
   pro produto, que filtra por igualdade exata.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "061"
down_revision: Union[str, None] = "060"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # level era varchar(12) e "area_ponderacao" tem 15 caracteres — o valor novo
    # simplesmente nao cabia ("value too long for type character varying(12)").
    # Ampliar VARCHAR e alteracao de catalogo: nao reescreve as 205 mil linhas.
    op.execute("ALTER TABLE census_geo ALTER COLUMN level TYPE varchar(20)")

    op.execute("ALTER TABLE census_geo ADD COLUMN IF NOT EXISTS cd_apond varchar(15)")
    op.execute("ALTER TABLE census_geo ADD COLUMN IF NOT EXISTS nm_apond varchar(160)")

    # updated_at: numa carga que roda por UF, ao longo de semanas, "quando este
    # setor foi atualizado pela ultima vez" e a pergunta operacional mais util
    # que existe. Em DUAS etapas de proposito: ADD COLUMN com DEFAULT now()
    # (funcao volatil) obrigaria o Postgres a REESCREVER as 205 mil linhas
    # segurando lock exclusivo; sem default a coluna e so catalogo, instantanea.
    # As linhas antigas ficam NULL — honesto: nunca foram atualizadas desde aqui.
    op.execute("ALTER TABLE census_geo ADD COLUMN IF NOT EXISTS updated_at timestamptz")
    op.execute("ALTER TABLE census_geo ALTER COLUMN updated_at SET DEFAULT now()")

    # Agregacao setor -> area de ponderacao. Parcial: hoje 100% das linhas tem
    # cd_apond NULL, e um indice cheio so ocuparia disco (que esta em 75%).
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_census_geo_apond ON census_geo (cd_apond) "
        "WHERE cd_apond IS NOT NULL"
    )

    op.execute("ALTER TABLE census_geo ALTER COLUMN geometry DROP NOT NULL")

    # NOT VALID: valida so o que entrar daqui pra frente, sem varrer as 205 mil
    # linhas existentes segurando lock. O VALIDATE seguinte roda com lock fraco.
    op.execute(
        "ALTER TABLE census_geo ADD CONSTRAINT ck_census_geo_level "
        "CHECK (level IN ('municipio','setor','area_ponderacao')) NOT VALID"
    )
    op.execute("ALTER TABLE census_geo VALIDATE CONSTRAINT ck_census_geo_level")


def downgrade() -> None:
    op.execute("ALTER TABLE census_geo DROP CONSTRAINT IF EXISTS ck_census_geo_level")
    # geometry volta a ser NOT NULL: so da certo se nao houver linha sem
    # geometria (o caso logo apos o upgrade). Com dado nacional carregado, o
    # downgrade falha de proposito — melhor do que apagar linha de censo.
    op.execute("ALTER TABLE census_geo ALTER COLUMN geometry SET NOT NULL")
    op.execute("DROP INDEX IF EXISTS ix_census_geo_apond")
    op.execute("ALTER TABLE census_geo DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE census_geo DROP COLUMN IF EXISTS nm_apond")
    op.execute("ALTER TABLE census_geo DROP COLUMN IF EXISTS cd_apond")
    # Encolher so e seguro depois que as linhas de area_ponderacao sumiram
    # (o CHECK acima ja foi removido, entao nao ha o que as recrie).
    op.execute("ALTER TABLE census_geo ALTER COLUMN level TYPE varchar(12)")
