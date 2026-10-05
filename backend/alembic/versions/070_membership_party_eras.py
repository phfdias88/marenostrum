"""Filiacao partidaria passa para a linha ATUAL do partido.

A migration 067 criou as linhas novas do 14 (MISSAO) e do 35 (DEMOCRATA) e
levou para elas os candidatos de 2025 em diante, mas deixou a filiacao presa as
linhas antigas. Filiacao e retrato de HOJE (o unico periodo carregado e
2026-05): os 23.719 filiados do numero 14 sao do Missao, e a pagina do
municipio os mostrava como "PTB".

O importador ja resolve isso para as proximas cargas (sem ano, vale a epoca
mais recente); esta migration conserta o que entrou antes.

Revision ID: 070
Revises: 069
"""
from alembic import op
import sqlalchemy as sa

revision = "070"
down_revision = "069"
branch_labels = None
depends_on = None

# Numeros com mais de uma linha: (linha antiga -> linha atual), ambas achadas
# pelo proprio banco. A atual e a de maior valid_from; as demais sao antigas.
_PARES = sa.text("""
    SELECT antiga.id AS antiga, atual.id AS atual
    FROM tse_parties antiga
    JOIN tse_parties atual
      ON atual.number = antiga.number
     AND atual.valid_from IS NOT NULL
     AND atual.valid_from = (
         SELECT max(p.valid_from) FROM tse_parties p WHERE p.number = antiga.number
     )
    WHERE antiga.id <> atual.id
""")


def _repontar(conn, de: str, para: str) -> None:
    for par in conn.execute(_PARES).mappings().all():
        origem, destino = par[de], par[para]
        # (party_id, municipality_id, period) e unico: se o destino ja tem a
        # mesma linha, a da origem sai em vez de colidir.
        conn.execute(sa.text("""
            DELETE FROM tse_party_membership o
            USING tse_party_membership d
            WHERE o.party_id = :origem AND d.party_id = :destino
              AND d.municipality_id = o.municipality_id AND d.period = o.period
        """), {"origem": origem, "destino": destino})
        conn.execute(
            sa.text("UPDATE tse_party_membership SET party_id = :destino "
                    "WHERE party_id = :origem"),
            {"origem": origem, "destino": destino},
        )


def upgrade() -> None:
    _repontar(op.get_bind(), de="antiga", para="atual")


def downgrade() -> None:
    # Devolve a filiacao a linha antiga — a 067 apaga a linha nova no proprio
    # downgrade, e a FK em cascata levaria a filiacao junto.
    _repontar(op.get_bind(), de="atual", para="antiga")
