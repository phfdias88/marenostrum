"""auditoria: log de quem editou/excluiu o quê (nível Mare Nostrum)

Revision ID: 038
Revises: 037
Create Date: 2026-06-27

Tabela audit_logs — registra create/update/delete por usuário/entidade, com
resumo legível. Base do nível de auditoria "Mare Nostrum" do PDF.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "038"
down_revision: Union[str, None] = "037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS audit_logs ("
        "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
        "  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,"
        "  user_id uuid NULL REFERENCES users(id) ON DELETE SET NULL,"
        "  user_name varchar(150) NULL,"
        "  user_role varchar(20) NULL,"
        "  action varchar(20) NOT NULL,"
        "  entity_type varchar(40) NOT NULL,"
        "  entity_id uuid NULL,"
        "  summary varchar(300) NULL,"
        "  meta jsonb NULL,"
        "  created_at timestamptz NOT NULL DEFAULT now()"
        ")"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_tenant_created "
        "ON audit_logs (tenant_id, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_tenant_entity "
        "ON audit_logs (tenant_id, entity_type)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_logs")
