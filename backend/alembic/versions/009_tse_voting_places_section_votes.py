"""tse: voting_places (bairro) + section_votes (por local)

Revision ID: 009
Revises: 008
Create Date: 2026-05-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- TseVotingPlace ---
    op.create_table(
        "tse_voting_places",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("local_code", sa.Integer(), nullable=False),
        sa.Column(
            "municipality_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tse_municipalities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("address", sa.String(300), nullable=True),
        sa.Column("neighborhood", sa.String(120), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("electors_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_tse_voting_places_muni_code",
        "tse_voting_places", ["municipality_id", "local_code"], unique=True,
    )
    op.create_index(
        "ix_tse_voting_places_muni_neighborhood",
        "tse_voting_places", ["municipality_id", "neighborhood"],
    )
    op.create_index(
        "ix_tse_voting_places_neighborhood",
        "tse_voting_places", ["neighborhood"],
    )

    # --- TseSectionVote ---
    op.create_table(
        "tse_section_votes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "candidate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tse_candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "voting_place_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tse_voting_places.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("votes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_tse_section_votes_unique",
        "tse_section_votes", ["candidate_id", "voting_place_id"], unique=True,
    )
    op.create_index(
        "ix_tse_section_votes_candidate",
        "tse_section_votes", ["candidate_id"],
    )
    op.create_index(
        "ix_tse_section_votes_place_votes",
        "tse_section_votes", ["voting_place_id", "votes"],
    )


def downgrade() -> None:
    op.drop_index("ix_tse_section_votes_place_votes", "tse_section_votes")
    op.drop_index("ix_tse_section_votes_candidate", "tse_section_votes")
    op.drop_index("ix_tse_section_votes_unique", "tse_section_votes")
    op.drop_table("tse_section_votes")

    op.drop_index("ix_tse_voting_places_neighborhood", "tse_voting_places")
    op.drop_index("ix_tse_voting_places_muni_neighborhood", "tse_voting_places")
    op.drop_index("ix_tse_voting_places_muni_code", "tse_voting_places")
    op.drop_table("tse_voting_places")
