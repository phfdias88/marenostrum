"""Senadores em exercicio, com a filiacao de hoje (dados abertos do Senado).

O TSE so sabe por qual partido o senador foi eleito. Troca de partido e
suplente em exercicio constam no Senado — e mudam a bancada "no mandato".

Revision ID: 071
Revises: 070
"""
from alembic import op
import sqlalchemy as sa

revision = "071"
down_revision = "070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "senate_sitting_members",
        sa.Column("id", sa.Uuid(), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("state", sa.String(2), nullable=False),
        sa.Column("party_abbr", sa.String(30), nullable=False),
        sa.Column("role", sa.String(30), nullable=True),
        sa.Column("term_end", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_senate_sitting_members_code", "senate_sitting_members",
        ["code"], unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_senate_sitting_members_code", "senate_sitting_members")
    op.drop_table("senate_sitting_members")
