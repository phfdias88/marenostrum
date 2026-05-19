"""tse: elections, parties, municipalities, candidates, vote_results, sync_jobs

Revision ID: 006
Revises: 005
Create Date: 2026-05-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Election --------------------------------------------------------
    op.create_table(
        "tse_elections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tse_code", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("type_name", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tse_code", name="uq_tse_elections_tse_code"),
    )
    op.create_index("ix_tse_elections_tse_code", "tse_elections", ["tse_code"])
    op.create_index("ix_tse_elections_year", "tse_elections", ["year"])

    # --- Party -----------------------------------------------------------
    op.create_table(
        "tse_parties",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("abbreviation", sa.String(20), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tse_parties_number", "tse_parties", ["number"], unique=True)

    # --- Municipality ----------------------------------------------------
    op.create_table(
        "tse_municipalities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tse_code", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("state", sa.String(2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tse_municipalities_tse_code", "tse_municipalities", ["tse_code"], unique=True)
    op.create_index("ix_tse_municipalities_state_name", "tse_municipalities", ["state", "name"])
    op.create_index("ix_tse_municipalities_name", "tse_municipalities", ["name"])
    op.create_index("ix_tse_municipalities_state", "tse_municipalities", ["state"])

    # --- Candidate -------------------------------------------------------
    op.create_table(
        "tse_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("sq_candidato", sa.Integer(), nullable=False),
        sa.Column("election_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tse_elections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("urn_name", sa.String(180), nullable=False),
        sa.Column("party_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tse_parties.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("office_code", sa.Integer(), nullable=False),
        sa.Column("office_name", sa.String(40), nullable=False),
        sa.Column("state", sa.String(2), nullable=False),
        sa.Column("situation", sa.String(40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tse_candidates_sq", "tse_candidates", ["sq_candidato"], unique=True)
    op.create_index("ix_tse_candidates_name", "tse_candidates", ["name"])
    op.create_index("ix_tse_candidates_urn_name", "tse_candidates", ["urn_name"])
    op.create_index("ix_tse_candidates_state", "tse_candidates", ["state"])
    op.create_index("ix_tse_candidates_office_code", "tse_candidates", ["office_code"])
    op.create_index("ix_tse_candidates_search", "tse_candidates", ["election_id", "state", "office_code"])

    # --- VoteResult ------------------------------------------------------
    op.create_table(
        "tse_vote_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tse_candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("municipality_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tse_municipalities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("votes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_tse_vote_results_unique",
        "tse_vote_results", ["candidate_id", "municipality_id"], unique=True,
    )
    op.create_index("ix_tse_vote_results_candidate", "tse_vote_results", ["candidate_id"])
    op.create_index("ix_tse_vote_results_municipality_votes", "tse_vote_results", ["municipality_id", "votes"])

    # --- Sync Job --------------------------------------------------------
    sync_status = postgresql.ENUM(
        "pending", "running", "completed", "failed",
        name="tse_sync_job_status", create_type=True,
    )
    sync_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "tse_sync_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset", sa.String(80), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("status",
                  postgresql.ENUM(name="tse_sync_job_status", create_type=False),
                  nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rows_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_total", sa.Integer(), nullable=True),
        sa.Column("candidates_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("parties_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("municipalities_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("vote_results_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tse_sync_jobs_status", "tse_sync_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_tse_sync_jobs_status", table_name="tse_sync_jobs")
    op.drop_table("tse_sync_jobs")
    sa.Enum(name="tse_sync_job_status").drop(op.get_bind(), checkfirst=True)
    op.drop_index("ix_tse_vote_results_municipality_votes", table_name="tse_vote_results")
    op.drop_index("ix_tse_vote_results_candidate", table_name="tse_vote_results")
    op.drop_index("ix_tse_vote_results_unique", table_name="tse_vote_results")
    op.drop_table("tse_vote_results")
    op.drop_index("ix_tse_candidates_search", table_name="tse_candidates")
    op.drop_index("ix_tse_candidates_office_code", table_name="tse_candidates")
    op.drop_index("ix_tse_candidates_state", table_name="tse_candidates")
    op.drop_index("ix_tse_candidates_urn_name", table_name="tse_candidates")
    op.drop_index("ix_tse_candidates_name", table_name="tse_candidates")
    op.drop_index("ix_tse_candidates_sq", table_name="tse_candidates")
    op.drop_table("tse_candidates")
    op.drop_index("ix_tse_municipalities_state", table_name="tse_municipalities")
    op.drop_index("ix_tse_municipalities_name", table_name="tse_municipalities")
    op.drop_index("ix_tse_municipalities_state_name", table_name="tse_municipalities")
    op.drop_index("ix_tse_municipalities_tse_code", table_name="tse_municipalities")
    op.drop_table("tse_municipalities")
    op.drop_index("ix_tse_parties_number", table_name="tse_parties")
    op.drop_table("tse_parties")
    op.drop_index("ix_tse_elections_year", table_name="tse_elections")
    op.drop_index("ix_tse_elections_tse_code", table_name="tse_elections")
    op.drop_table("tse_elections")
