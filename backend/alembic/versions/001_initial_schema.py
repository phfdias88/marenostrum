"""initial schema: tenants, users, contacts

Revision ID: 001
Revises:
Create Date: 2026-05-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------------- tenants ----------------------
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(60), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"], unique=True)

    # ---------------------- enums ------------------------
    user_role = postgresql.ENUM(
        "owner", "manager", "staff", "volunteer",
        name="user_role", create_type=True,
    )
    user_role.create(op.get_bind(), checkfirst=True)

    contact_type = postgresql.ENUM(
        "voter", "leader", "supporter", "donor", "other",
        name="contact_type", create_type=True,
    )
    contact_type.create(op.get_bind(), checkfirst=True)

    # ---------------------- users ------------------------
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("full_name", sa.String(150), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM(name="user_role", create_type=False),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_tenant_id_id", "users", ["tenant_id", "id"])

    # ---------------------- contacts ---------------------
    op.create_table(
        "contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("full_name", sa.String(150), nullable=False),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(2), nullable=True),
        sa.Column(
            "type",
            postgresql.ENUM(name="contact_type", create_type=False),
            nullable=False,
        ),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_contacts_tenant_id", "contacts", ["tenant_id"])
    op.create_index("ix_contacts_phone", "contacts", ["phone"])
    op.create_index("ix_contacts_tenant_id_id", "contacts", ["tenant_id", "id"])
    op.create_index("ix_contacts_tenant_name", "contacts", ["tenant_id", "full_name"])


def downgrade() -> None:
    op.drop_index("ix_contacts_tenant_name", table_name="contacts")
    op.drop_index("ix_contacts_tenant_id_id", table_name="contacts")
    op.drop_index("ix_contacts_phone", table_name="contacts")
    op.drop_index("ix_contacts_tenant_id", table_name="contacts")
    op.drop_table("contacts")

    op.drop_index("ix_users_tenant_id_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_tenant_id", table_name="users")
    op.drop_table("users")

    sa.Enum(name="contact_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)

    op.drop_index("ix_tenants_slug", table_name="tenants")
    op.drop_table("tenants")
