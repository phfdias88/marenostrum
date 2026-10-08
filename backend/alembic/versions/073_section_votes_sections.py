"""tse_section_votes.sections: o voto por SECAO dentro do local.

A tabela guarda uma linha por (candidato, local) com as secoes ja somadas. A
planilha de dados brutos do candidato ganhou uma aba por secao eleitoral, e o
detalhe que era descartado na carga passa a ficar aqui: {"<NR_SECAO>": votos}.

SO A COLUNA. Nula e sem default, entao o Postgres nao reescreve a tabela (sao
quase 3 GB): e uma mudanca de catalogo. Quem preenche e
scripts/carregar_votacao_secao.py, UF por UF, fora da migration.

Revision ID: 073
Revises: 072
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "073"
down_revision = "072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # O ALTER pede a tabela so para ele por um instante. Se alguem estiver com
    # uma consulta longa nela, falhar em 15s e melhor que ficar na fila
    # travando todo mundo que chega depois (o entrypoint tenta de novo).
    op.execute("SET LOCAL lock_timeout = '15s'")
    op.add_column(
        "tse_section_votes",
        sa.Column("sections", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tse_section_votes", "sections")
