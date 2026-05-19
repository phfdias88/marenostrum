"""tse: sq_candidato INTEGER -> BIGINT (TSE usa IDs de 12-13 digitos)

Revision ID: 007
Revises: 006
Create Date: 2026-05-19

Bug encontrado no primeiro sync: psycopg.errors.NumericValueOutOfRange.
SQ_CANDIDATO no TSE 2024 é tipicamente 250001595870 (12 digitos),
excede PG INTEGER (max 2_147_483_647 = 10 digitos).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "tse_candidates",
        "sq_candidato",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )


def downgrade() -> None:
    # CAVEAT: vai estourar overflow se algum valor > 2^31 ja foi inserido.
    op.alter_column(
        "tse_candidates",
        "sq_candidato",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
    )
