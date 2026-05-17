"""contact: address, neighborhood, lat/lng, birth_date + unique phone por tenant

Revision ID: 002
Revises: 001
Create Date: 2026-05-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Novas colunas (todas nullable — nao quebra dados existentes)
    op.add_column("contacts", sa.Column("address", sa.String(255), nullable=True))
    op.add_column("contacts", sa.Column("neighborhood", sa.String(100), nullable=True))
    op.add_column("contacts", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("contacts", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column("contacts", sa.Column("birth_date", sa.Date(), nullable=True))

    # Unicidade de telefone DENTRO do tenant.
    # ATENCAO: se ja houver dados duplicados, isso falha. Em prod faria limpeza antes.
    op.create_unique_constraint(
        "uq_contacts_tenant_phone",
        "contacts",
        ["tenant_id", "phone"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_contacts_tenant_phone", "contacts", type_="unique")
    op.drop_column("contacts", "birth_date")
    op.drop_column("contacts", "longitude")
    op.drop_column("contacts", "latitude")
    op.drop_column("contacts", "neighborhood")
    op.drop_column("contacts", "address")
