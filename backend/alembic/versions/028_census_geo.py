"""censo: setores censitários com geometria + dados (POC IBGE)

Revision ID: 028
Revises: 027
Create Date: 2026-06-05

POC de dados censitários (IBGE Censo 2022). Guarda setores censitários com a
geometria (GeoJSON em JSONB) + hierarquia (município/distrito/subdistrito/
bairro) + indicadores do agregado básico (população, domicílios). Sem PostGIS
nesta fase — a renderização é client-side (Leaflet). Em produção, evoluir para
PostGIS + vector tiles dado o volume (~450k setores no Brasil).
"""
from typing import Sequence, Union

from alembic import op


revision: str = "028"
down_revision: Union[str, None] = "027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS census_geo ("
        "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
        "  level varchar(12) NOT NULL DEFAULT 'setor',"
        "  cd_setor varchar(20) NOT NULL,"
        "  cd_mun varchar(7),"
        "  nm_mun varchar(80),"
        "  cd_dist varchar(12),"
        "  nm_dist varchar(80),"
        "  nm_subdist varchar(80),"
        "  nm_bairro varchar(160),"
        "  situacao varchar(20),"
        "  area_km2 double precision,"
        "  populacao integer,"
        "  domicilios integer,"
        "  geometry jsonb NOT NULL,"
        "  created_at timestamptz NOT NULL DEFAULT now(),"
        "  CONSTRAINT uq_census_geo_setor UNIQUE (cd_setor)"
        ")"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_census_geo_mun ON census_geo (cd_mun)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS census_geo")
