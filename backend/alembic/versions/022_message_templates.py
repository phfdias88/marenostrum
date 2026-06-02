"""crm: templates de mensagem (WhatsApp) por tenant

Revision ID: 022
Revises: 021
Create Date: 2026-06-02

Onda 3 (20B): mensagens reutilizáveis com variáveis ({nome}, {cidade}, etc.)
pra disparar via WhatsApp pros contatos. Tenant-scoped.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS message_templates ("
        "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
        "  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,"
        "  title varchar(120) NOT NULL,"
        "  body varchar(2000) NOT NULL,"
        "  category varchar(40) NULL,"
        "  created_at timestamptz NOT NULL DEFAULT now(),"
        "  updated_at timestamptz NOT NULL DEFAULT now()"
        ")"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_message_templates_tenant "
        "ON message_templates (tenant_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_message_templates_tenant")
    op.execute("DROP TABLE IF EXISTS message_templates")
