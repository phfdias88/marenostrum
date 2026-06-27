"""acesso Mare Nostrum: flag is_superadmin (auditoria cross-tenant)

Revision ID: 040
Revises: 039
Create Date: 2026-06-27

Flag de super-acesso da CONSULTORIA (Mare Nostrum) — vê a auditoria de TODAS as
campanhas (cross-tenant), pra responsabilizar quem editou/excluiu o quê. NÃO
tem endpoint pra ligar (anti-escalonamento): é setado só direto no banco pela
equipe Mare Nostrum. Default false.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "040"
down_revision: Union[str, None] = "039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
        "is_superadmin boolean NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS is_superadmin")
