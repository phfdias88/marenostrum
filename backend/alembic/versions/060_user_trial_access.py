"""users.usage_limit_hours/first_login_at/expires_at — acesso temporário (trial)

Contas de teste/demonstração com tempo de uso limitado. O relógio só começa no
PRIMEIRO login (first_login_at); expires_at = first_login_at + usage_limit_hours.
Todas as colunas são NULL por padrão — usuários existentes ficam ILIMITADOS.

Revision ID: 060
Revises: 059
"""
from typing import Sequence, Union

from alembic import op

revision: str = "060"
down_revision: Union[str, None] = "059"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # double precision aceita frações de hora (ex: 2.5). timestamptz p/ instantes
    # absolutos (o cap do trial compara com NOW() em UTC).
    op.execute(
        "ALTER TABLE users "
        "ADD COLUMN IF NOT EXISTS usage_limit_hours double precision, "
        "ADD COLUMN IF NOT EXISTS first_login_at timestamptz, "
        "ADD COLUMN IF NOT EXISTS expires_at timestamptz"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE users "
        "DROP COLUMN IF EXISTS expires_at, "
        "DROP COLUMN IF EXISTS first_login_at, "
        "DROP COLUMN IF EXISTS usage_limit_hours"
    )
