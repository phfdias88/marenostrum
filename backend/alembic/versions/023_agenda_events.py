"""crm: agenda parlamentar geo-localizada

Revision ID: 023
Revises: 022
Create Date: 2026-06-02

Onda 3 (20C): eventos/compromissos da agenda com data, local e
geolocalização (lat/lng) — pra visualizar no mapa + lista cronológica.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS agenda_events ("
        "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
        "  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,"
        "  title varchar(160) NOT NULL,"
        "  description varchar(2000) NULL,"
        "  starts_at timestamptz NOT NULL,"
        "  location_name varchar(160) NULL,"
        "  address varchar(255) NULL,"
        "  city varchar(100) NULL,"
        "  state varchar(2) NULL,"
        "  latitude double precision NULL,"
        "  longitude double precision NULL,"
        "  category varchar(40) NULL,"
        "  created_at timestamptz NOT NULL DEFAULT now(),"
        "  updated_at timestamptz NOT NULL DEFAULT now()"
        ")"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agenda_tenant_starts "
        "ON agenda_events (tenant_id, starts_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_agenda_tenant_starts")
    op.execute("DROP TABLE IF EXISTS agenda_events")
