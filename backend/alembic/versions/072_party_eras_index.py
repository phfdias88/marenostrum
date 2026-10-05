"""tse_parties: unico por (numero, sigla, EPOCA).

A 067 deixou o indice unico em (number, abbreviation). Isso basta enquanto cada
sigla aparece uma vez por numero — e deixa de bastar no 22, que foi PL, virou
PR e voltou a ser PL: sao duas linhas "PL", a de 2002-2006 e a de hoje.

O terceiro campo e coalesce(valid_from, 0), nao valid_from puro: NULL nunca e
igual a NULL num indice unico, entao duas linhas "desde sempre" do mesmo numero
e sigla passariam caladas (e qual delas e "a de hoje" passaria a depender da
ordem em que o banco devolve as linhas).

SO O INDICE. As linhas das epocas e o reponte das candidaturas antigas ficam em
scripts/epocas_de_partido.py: sao ~280 mil UPDATEs numa coluna indexada, e
migration roda no entrypoint, antes da API subir, numa transacao so.

Revision ID: 072
Revises: 071
"""
from alembic import op
import sqlalchemy as sa

revision = "072"
down_revision = "071"
branch_labels = None
depends_on = None

_INDICE = "ix_tse_parties_number_sigla"


def upgrade() -> None:
    # A tabela tem ~40 linhas: recriar o indice e instantaneo. O lock_timeout e
    # so para nao ficar esperando atras de uma transacao longa da captura.
    op.execute("SET LOCAL lock_timeout = '10s'")
    op.drop_index(_INDICE, table_name="tse_parties")
    op.create_index(
        _INDICE, "tse_parties",
        ["number", "abbreviation", sa.text("coalesce(valid_from, 0)")],
        unique=True,
    )


def downgrade() -> None:
    # O indice antigo nao aceita duas linhas com a mesma sigla no mesmo numero.
    # Se as epocas ja foram criadas, e preciso desfaze-las ANTES (e isso nao e
    # trabalho de migration: reponta 280 mil candidaturas).
    repetidas = op.get_bind().execute(sa.text("""
        SELECT number, abbreviation FROM tse_parties
        GROUP BY number, abbreviation HAVING count(*) > 1
    """)).all()
    if repetidas:
        raise RuntimeError(
            "Ha numero com duas linhas da mesma sigla "
            f"({', '.join(f'{n}/{s}' for n, s in repetidas)}). Rode antes: "
            "python - --desfazer < backend/scripts/epocas_de_partido.py"
        )
    op.execute("SET LOCAL lock_timeout = '10s'")
    op.drop_index(_INDICE, table_name="tse_parties")
    op.create_index(_INDICE, "tse_parties", ["number", "abbreviation"], unique=True)
