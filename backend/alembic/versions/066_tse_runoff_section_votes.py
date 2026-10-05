"""Voto de 2o turno por LOCAL de votacao (analise por bairro no 2o turno).

O importador de secao descartava tudo que nao fosse 1o turno, e a chave de
tse_section_votes e (candidato, local), sem turno. Sem esta tabela o produto
perde a leitura por bairro justamente no 2o turno.

Revision ID: 066
Revises: 065
"""
from alembic import op
import sqlalchemy as sa

revision = "066"
down_revision = "065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tse_runoff_section_votes",
        sa.Column("id", sa.Uuid(), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("voting_place_id", sa.Uuid(), nullable=False),
        sa.Column("votes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["tse_candidates.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["voting_place_id"], ["tse_voting_places.id"],
                                ondelete="CASCADE"),
    )
    op.create_index("ix_tse_runoff_section_unique", "tse_runoff_section_votes",
                    ["candidate_id", "voting_place_id"], unique=True)
    op.create_index("ix_tse_runoff_section_place", "tse_runoff_section_votes",
                    ["voting_place_id", "votes"])


def downgrade() -> None:
    op.drop_index("ix_tse_runoff_section_place", "tse_runoff_section_votes")
    op.drop_index("ix_tse_runoff_section_unique", "tse_runoff_section_votes")
    op.drop_table("tse_runoff_section_votes")
