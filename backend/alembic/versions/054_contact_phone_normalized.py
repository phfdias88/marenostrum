"""contacts.phone_normalized — telefone canonizado pro auto-vinculo do webhook

O webhook BotConversa manda "5521999991234" e o CRM grava "(21) 99999-1234";
a comparacao exata de find_by_phone nunca casava. Esta migration cria a coluna
canonica (so' digitos, sem DDI 55), indice composto por tenant e backfill em
SQL puro com a MESMA regra de app/utils/phone.py::normalize_phone:
- so' digitos (regexp_replace)
- comeca com 55 e tem 12-13 digitos -> remove o DDI
- menos de 8 digitos -> NULL (nao e' telefone util)

IF NOT EXISTS: idempotente caso a coluna/indice ja' tenham sido criados
manualmente em producao antes do deploy.

Revision ID: 054
Revises: 053
"""
from typing import Sequence, Union

from alembic import op

revision: str = "054"
down_revision: Union[str, None] = "053"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Backfill: regra identica a normalize_phone() (utils/phone.py).
# left(..., 20) = defensiva pro varchar(20) com input-lixo de 30 chars.
_BACKFILL_SQL = r"""
UPDATE contacts SET phone_normalized = left(
    CASE
        WHEN regexp_replace(phone, '\D', '', 'g') LIKE '55%'
             AND length(regexp_replace(phone, '\D', '', 'g')) BETWEEN 12 AND 13
        THEN substr(regexp_replace(phone, '\D', '', 'g'), 3)
        ELSE regexp_replace(phone, '\D', '', 'g')
    END, 20)
WHERE phone IS NOT NULL
"""


def upgrade() -> None:
    op.execute(
        "ALTER TABLE contacts ADD COLUMN IF NOT EXISTS phone_normalized varchar(20)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_contacts_tenant_phone_norm "
        "ON contacts (tenant_id, phone_normalized)"
    )
    op.execute(_BACKFILL_SQL)
    # Menos de 8 digitos = nao e' telefone util (mesma regra do normalize_phone)
    op.execute(
        "UPDATE contacts SET phone_normalized = NULL "
        "WHERE phone_normalized IS NOT NULL AND length(phone_normalized) < 8"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_contacts_tenant_phone_norm")
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS phone_normalized")
