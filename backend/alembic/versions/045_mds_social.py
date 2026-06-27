"""mds: CadÚnico + Bolsa Família por município (MDS/SAGI MI Social)

Revision ID: 045
Revises: 044
Create Date: 2026-06-27

Tabela GLOBAL (dado público MDS, sem tenant_id) — série mensal por município:
inscritos no CadÚnico + beneficiários do Bolsa Família. Chave (cd_mun, anomes).
cd_mun em 7 dígitos (reconstruído do codigo_ibge de 6 do MDS) pra casar com
census_geo e tse_municipalities. Populado por scripts/ingest_mds_social.py.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "045"
down_revision: Union[str, None] = "044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS mds_social_municipio ("
        "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
        "  cd_mun varchar(7) NOT NULL,"
        "  anomes varchar(6) NOT NULL,"
        "  cadunico_familias integer,"
        "  cadunico_pessoas integer,"
        "  pbf_familias integer,"
        "  pbf_pessoas integer,"
        "  pbf_valor double precision,"
        "  created_at timestamptz NOT NULL DEFAULT now(),"
        "  CONSTRAINT uq_mds_social_mun_mes UNIQUE (cd_mun, anomes)"
        ")"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_mds_social_mun ON mds_social_municipio (cd_mun)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mds_social_municipio")
