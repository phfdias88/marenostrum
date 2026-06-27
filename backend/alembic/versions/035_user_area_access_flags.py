"""users.*_enabled — acesso por área configurável pelo owner

Revision ID: 035
Revises: 034
Create Date: 2026-06-17

O owner liga/desliga, por usuário, o acesso a cada área (Análises/TSE, Painel,
Mapa da Campanha, Demandas, Agenda). Default TRUE — preserva o acesso amplo que
Coordenador/Equipe já tinham; o owner desliga o que quiser por pessoa.
(census_enabled já existe desde a 029, com default FALSE.)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "035"
down_revision: Union[str, None] = "034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLS = ("analytics_enabled", "panel_enabled", "map_enabled", "demands_enabled", "agenda_enabled")


def upgrade() -> None:
    for col in _COLS:
        op.add_column(
            "users",
            sa.Column(col, sa.Boolean(), nullable=False, server_default=sa.true()),
        )


def downgrade() -> None:
    for col in _COLS:
        op.drop_column("users", col)
