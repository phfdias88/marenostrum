"""contacts: whatsapp, instagram, facebook, cep

Revision ID: 033
Revises: 032
Create Date: 2026-06-16

Campos novos no cadastro de contato (pedido do cliente):
- whatsapp separado do telefone (fixo x zap)
- instagram / facebook (redes sociais)
- cep (endereço)
Todos nullable — não quebra os contatos existentes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "033"
down_revision: Union[str, None] = "032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLS = [
    ("whatsapp", sa.String(length=30)),
    ("instagram", sa.String(length=120)),
    ("facebook", sa.String(length=200)),
    ("cep", sa.String(length=9)),
]


def upgrade() -> None:
    for name, col_type in COLS:
        op.add_column("contacts", sa.Column(name, col_type, nullable=True))


def downgrade() -> None:
    for name, _ in COLS:
        op.drop_column("contacts", name)
