"""contacts.created_by_user_id + created_by_name — quem cadastrou o contato

Revision ID: 036
Revises: 035
Create Date: 2026-06-17

Rastreia qual usuário (liderança/membro) cadastrou cada contato, pro owner
filtrar/exibir "cadastrado por". Guarda o id (FK SET NULL) + o nome
denormalizado. Contatos antigos ficam com NULL.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "036"
down_revision: Union[str, None] = "035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("contacts", sa.Column("created_by_user_id", sa.UUID(), nullable=True))
    op.add_column("contacts", sa.Column("created_by_name", sa.String(length=150), nullable=True))
    op.create_foreign_key(
        "fk_contacts_created_by_user",
        "contacts",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_contacts_tenant_created_by",
        "contacts",
        ["tenant_id", "created_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_contacts_tenant_created_by", table_name="contacts")
    op.drop_constraint("fk_contacts_created_by_user", "contacts", type_="foreignkey")
    op.drop_column("contacts", "created_by_name")
    op.drop_column("contacts", "created_by_user_id")
