"""adversarios: tabela monitored_candidates

Revision ID: 021
Revises: 020
Create Date: 2026-05-30

Wave 2 (candidato/campanha): persiste lista de candidatos que o usuario
monitora — "meu candidato" + "adversarios" — pra mostrar comparativo
persistente no dashboard e (futuro) alertas em mudancas.

Decisao por tabela propria (e nao 'favoritos' do TSE):
- Favoritos = leitura/curadoria pessoal sem semantica de papel
- Monitored = papel definido (meu vs adversario) + label custom + cor
- Permite agregar/comparar de forma sticky sem reselecionar
"""
from typing import Sequence, Union

from alembic import op


revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS monitored_candidates ("
        "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
        "  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,"
        # candidate_id da tse_candidates (uuid). NAO usa FK forte pra
        # nao trancar exclusao em re-sync — adversario "orfao" e' ok
        # (mostra label custom + flag candidato_removido).
        "  candidate_id uuid NOT NULL,"
        "  label varchar(80) NULL,"
        "  is_mine boolean NOT NULL DEFAULT false,"
        "  color varchar(16) NULL,"
        "  notes varchar(1000) NULL,"
        "  created_at timestamptz NOT NULL DEFAULT now(),"
        "  updated_at timestamptz NOT NULL DEFAULT now()"
        ")"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_monitored_tenant_candidate "
        "ON monitored_candidates (tenant_id, candidate_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_monitored_tenant_mine "
        "ON monitored_candidates (tenant_id, is_mine)"
    )
    # Apenas UM candidato com is_mine=true por tenant — regra de negocio
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_monitored_tenant_one_mine "
        "ON monitored_candidates (tenant_id) WHERE is_mine = true"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_monitored_tenant_one_mine")
    op.execute("DROP INDEX IF EXISTS ix_monitored_tenant_mine")
    op.execute("DROP INDEX IF EXISTS uq_monitored_tenant_candidate")
    op.execute("DROP TABLE IF EXISTS monitored_candidates")
