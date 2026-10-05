"""tse_turnout ganha o total de votos do cargo.

Brancos e nulos sao divididos pelo TOTAL DE VOTOS, e a migration 068 nao o
guardava: a conta usava validos + brancos + nulos. Falta ali o voto ANULADO
(candidato com registro indeferido ou sub judice), que nao e valido nem nulo.
Onde ele existe o percentual saia maior que o do TSE — governador do RJ em
2026 dava 5,24% de brancos contra os 5,09% oficiais.

Revision ID: 069
Revises: 068
"""
from alembic import op
import sqlalchemy as sa

revision = "069"
down_revision = "068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tse_turnout", sa.Column("total_votes", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("tse_turnout", "total_votes")
