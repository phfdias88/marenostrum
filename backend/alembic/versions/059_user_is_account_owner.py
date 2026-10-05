"""users.is_account_owner — TITULAR da assinatura vs convidado

O PO precisa distinguir quem PAGOU a plataforma (titular, criado pelo webhook
de billing) dos usuários convidados pelo painel de equipe — inclusive quando
um convidado é promovido a "Administrador (Dono)" (role=owner): papel dá
PERMISSÃO, a flag marca a TITULARIDADE da conta.

Backfill: em cada tenant, o OWNER ativo mais antigo vira o titular (é quem
abriu a conta). Tenants novos: o webhook do Asaas provisiona o comprador já
com is_account_owner=true (services/provisioning.py).

Revision ID: 059
Revises: 058
"""
from typing import Sequence, Union

from alembic import op

revision: str = "059"
down_revision: Union[str, None] = "058"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
        "is_account_owner boolean NOT NULL DEFAULT false"
    )
    # Backfill: 1 titular por tenant = o owner ATIVO mais antigo.
    op.execute(
        "UPDATE users SET is_account_owner = true WHERE id IN ("
        "  SELECT DISTINCT ON (tenant_id) id FROM users "
        "  WHERE role = 'owner' AND is_active "
        "  ORDER BY tenant_id, created_at ASC"
        ")"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS is_account_owner")
