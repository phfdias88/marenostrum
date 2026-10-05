"""Voto do 2o turno ganha tabela propria.

A chave de tse_vote_results e (candidato, municipio), sem turno, entao o
importador DESCARTA toda linha de NR_TURNO=2 — somar os dois turnos no mesmo
registro faria Lula 2022 aparecer com 117 milhoes em vez de 57.

Na pratica: no dia do 2o turno o sistema importaria o arquivo e jogaria fora
cada voto. Esta tabela conserta isso sem tocar nas 23,8 milhoes de linhas de
tse_vote_results nem mudar o comportamento de nenhuma consulta existente.

Revision ID: 065
Revises: 064
"""
from alembic import op
import sqlalchemy as sa

revision = "065"
down_revision = "064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tse_runoff_votes",
        sa.Column("id", sa.Uuid(), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("municipality_id", sa.Uuid(), nullable=False),
        sa.Column("votes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["tse_candidates.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["municipality_id"], ["tse_municipalities.id"],
                                ondelete="CASCADE"),
    )
    op.create_index(
        "ix_tse_runoff_votes_unique", "tse_runoff_votes",
        ["candidate_id", "municipality_id"], unique=True,
    )
    op.create_index(
        "ix_tse_runoff_votes_municipality", "tse_runoff_votes",
        ["municipality_id", "votes"],
    )


def downgrade() -> None:
    op.drop_index("ix_tse_runoff_votes_municipality", "tse_runoff_votes")
    op.drop_index("ix_tse_runoff_votes_unique", "tse_runoff_votes")
    op.drop_table("tse_runoff_votes")
