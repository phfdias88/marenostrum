"""Comparecimento, abstencao, brancos e nulos por cargo e UF.

Tudo o que o sistema guardava do TSE era voto nominal, por candidato. Abstencao,
branco e nulo nao pertencem a candidato nenhum — sem esta tabela nao havia como
responder "quantos nao foram votar" nem mostrar quanto da apuracao ja entrou.

Revision ID: 068
Revises: 067
"""
from alembic import op
import sqlalchemy as sa

revision = "068"
down_revision = "067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tse_turnout",
        sa.Column("id", sa.Uuid(), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("office_code", sa.Integer(), nullable=False),
        sa.Column("uf", sa.String(2), nullable=False),
        sa.Column("electorate", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("turnout", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("abstention", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("valid_votes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("blank_votes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("null_votes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("sections_total", sa.Integer(), nullable=True),
        sa.Column("sections_counted", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_tse_turnout_unique", "tse_turnout",
        ["year", "round", "office_code", "uf"], unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_tse_turnout_unique", "tse_turnout")
    op.drop_table("tse_turnout")
