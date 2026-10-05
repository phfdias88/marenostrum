"""Partido por epoca: o numero deixa de ser unico em tse_parties.

O TSE reaproveita numero de partido e partido troca de nome. Com uma linha por
numero, a eleicao de 2026 saia com sigla de outra epoca: o candidato a
presidente do MISSAO (numero 14) aparecia como "PTB", partido extinto em 2023,
e os 467 candidatos do DEMOCRATA (35) apareciam como "PMB".

Esta migration:
  1. cria `valid_from` (primeiro ano em que a sigla responde pelo numero);
  2. troca o indice unico de (number) por (number, abbreviation);
  3. cria as duas linhas novas que 2026 exige e passa para elas os candidatos
     de 2025 em diante. Siglas e nomes vem do consulta_cand_2026 do TSE.

Quem resolve "qual linha vale" dali em diante e app/utils/partidos.py.

Revision ID: 067
Revises: 066
"""
from alembic import op
import sqlalchemy as sa

revision = "067"
down_revision = "066"
branch_labels = None
depends_on = None

# (numero, sigla nova, nome novo, vale a partir de)
EPOCAS = (
    (14, "MISSÃO", "PARTIDO MISSÃO", 2025),
    (35, "DEMOCRATA", "DEMOCRATA", 2025),
)


def upgrade() -> None:
    op.add_column("tse_parties", sa.Column("valid_from", sa.Integer(), nullable=True))
    op.drop_index("ix_tse_parties_number", table_name="tse_parties")
    op.create_index("ix_tse_parties_number", "tse_parties", ["number"])
    op.create_index(
        "ix_tse_parties_number_sigla", "tse_parties",
        ["number", "abbreviation"], unique=True,
    )

    conn = op.get_bind()
    for numero, sigla, nome, desde in EPOCAS:
        antiga = conn.execute(
            sa.text("SELECT id, abbreviation FROM tse_parties WHERE number = :n"),
            {"n": numero},
        ).first()
        # Banco sem o partido antigo (instalacao nova): nada a corrigir — o
        # importador ja cria a linha com a sigla que o arquivo trouxer.
        if antiga is None or antiga.abbreviation == sigla:
            continue
        nova = conn.execute(
            sa.text("""
                INSERT INTO tse_parties
                    (id, number, abbreviation, name, valid_from, created_at, updated_at)
                VALUES
                    (gen_random_uuid(), :n, :sigla, :nome, :desde, now(), now())
                RETURNING id
            """),
            {"n": numero, "sigla": sigla, "nome": nome, "desde": desde},
        ).scalar()
        conn.execute(
            sa.text("""
                UPDATE tse_candidates c
                SET party_id = :nova
                FROM tse_elections e
                WHERE e.id = c.election_id
                  AND e.year >= :desde
                  AND c.party_id = :antiga
            """),
            {"nova": nova, "antiga": antiga.id, "desde": desde},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for numero, sigla, _nome, _desde in EPOCAS:
        nova = conn.execute(
            sa.text("SELECT id FROM tse_parties WHERE number = :n AND abbreviation = :s"),
            {"n": numero, "s": sigla},
        ).scalar()
        antiga = conn.execute(
            sa.text("""
                SELECT id FROM tse_parties
                WHERE number = :n AND abbreviation <> :s AND valid_from IS NULL
            """),
            {"n": numero, "s": sigla},
        ).scalar()
        if nova is None or antiga is None:
            continue
        conn.execute(
            sa.text("UPDATE tse_candidates SET party_id = :a WHERE party_id = :n"),
            {"a": antiga, "n": nova},
        )
        conn.execute(sa.text("DELETE FROM tse_parties WHERE id = :n"), {"n": nova})

    op.drop_index("ix_tse_parties_number_sigla", table_name="tse_parties")
    op.drop_index("ix_tse_parties_number", table_name="tse_parties")
    op.create_index("ix_tse_parties_number", "tse_parties", ["number"], unique=True)
    op.drop_column("tse_parties", "valid_from")
