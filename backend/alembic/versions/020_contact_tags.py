"""contacts: coluna `tags` JSONB + indice GIN

Revision ID: 020
Revises: 019
Create Date: 2026-05-30

Wave 1 (gabinete/campanha): permite segmentar contatos por etiquetas
livres ("doador-2024", "lideranca-bairro-x", "voluntario", etc.).

Decisao por JSONB array de strings (e nao tabela auxiliar):
- Multi-tenant ja' filtra por tenant_id — nao precisamos de FK forte
- Frontend faz contains/intersection diretamente — GIN cobre
- Adicionar/remover tag = 1 UPDATE, sem JOIN nem CRUD em outra tabela
- Backup/restore trivial (vai no mesmo row)

Indice GIN com jsonb_path_ops e' ~2x mais rapido que GIN padrao
para o nosso unico caso de uso (`tags @> '["x"]'`) e ocupa metade
do espaco. Trade-off: nao suporta key-exists `?`, mas nao usamos.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE contacts ADD COLUMN IF NOT EXISTS tags jsonb NOT NULL DEFAULT '[]'::jsonb"
    )
    # GIN com jsonb_path_ops — otimizado para `tags @> '["x"]'`
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_contacts_tags_gin "
        "ON contacts USING gin (tags jsonb_path_ops)"
    )
    # Indice combinado pra (mes, dia) de birth_date — usado pelo widget
    # de aniversariantes. Expression index com EXTRACT.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_contacts_birthday_md "
        "ON contacts (tenant_id, "
        "(EXTRACT(MONTH FROM birth_date)), "
        "(EXTRACT(DAY FROM birth_date))) "
        "WHERE birth_date IS NOT NULL AND is_active = true"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_contacts_birthday_md")
    op.execute("DROP INDEX IF EXISTS ix_contacts_tags_gin")
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS tags")
