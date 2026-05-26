"""tse: votos do candidato por zona eleitoral

Revision ID: 017
Revises: 016
Create Date: 2026-05-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tse_candidate_zone_votes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("municipality_id", sa.UUID(), nullable=False),
        sa.Column("zone", sa.Integer(), nullable=False),
        sa.Column("votes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["tse_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["municipality_id"], ["tse_municipalities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tse_zone_votes_unique",
        "tse_candidate_zone_votes",
        ["candidate_id", "municipality_id", "zone"],
        unique=True,
    )
    op.create_index(
        "ix_tse_zone_votes_candidate",
        "tse_candidate_zone_votes",
        ["candidate_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tse_zone_votes_candidate", table_name="tse_candidate_zone_votes")
    op.drop_index("ix_tse_zone_votes_unique", table_name="tse_candidate_zone_votes")
    op.drop_table("tse_candidate_zone_votes")
