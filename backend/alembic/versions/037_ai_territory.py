"""ia: inteligência de território (contatos da campanha × eleitorado × adversário)

Revision ID: 037
Revises: 036
Create Date: 2026-06-27

Cache da análise "Inteligência de Território" da Maré IA. DIFERENTE de
ai_reports/ai_comparisons (cache GLOBAL por candidato, pois só usam dado
público do TSE), esta análise cruza os CONTATOS PRIVADOS do tenant (CRM) com
o eleitorado e os votos — então o cache é ISOLADO POR TENANT, chaveado por
(tenant_id, candidate_id, adversary_id). Nunca é servido a outro tenant.

contacts_snapshot guarda a contagem de contatos ativos do tenant no momento
da geração — se mudar (cadastraram/removeram contatos), o cache é refeito.
votes_snapshot faz o mesmo pro re-sync do TSE.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "037"
down_revision: Union[str, None] = "036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS ai_territory ("
        "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
        "  tenant_id uuid NOT NULL,"
        "  candidate_id uuid NOT NULL,"
        "  adversary_id uuid NOT NULL,"
        "  content jsonb NOT NULL,"
        "  model varchar(40) NULL,"
        "  contacts_snapshot integer NOT NULL DEFAULT 0,"
        "  votes_snapshot bigint NOT NULL DEFAULT 0,"
        "  created_at timestamptz NOT NULL DEFAULT now(),"
        "  CONSTRAINT uq_ai_territory UNIQUE (tenant_id, candidate_id, adversary_id)"
        ")"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ai_territory")
