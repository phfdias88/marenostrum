"""
TseSectionVote — votos de UM candidato em UM local de votacao
(agregado de todas as secoes do mesmo local).

A linha continua sendo (candidato, local): bairro e local sao a granularidade
de toda tela, e uma linha por secao multiplicaria a tabela por ~4 (RJ 2026:
1,8 mi de pares candidato x local, 6,8 mi de pares candidato x secao).

O detalhe por secao (NR_SECAO) mora em `sections`, na propria linha, so para a
exportacao em planilha. E opcional: carga antiga e a que veio do job da API
nao tem (ver app/services/votacao_secao.py, que e quem preenche).

Fonte: `votacao_secao_<ano>_<UF>.zip`.
"""
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, Index, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# JSONB no Postgres, JSON no SQLite da suite (coluna so-Postgres derruba o
# create_all e a suite inteira junto).
_JSONB = JSON().with_variant(JSONB, "postgresql")


class TseSectionVote(Base, TimestampMixin):
    __tablename__ = "tse_section_votes"

    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("tse_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )

    voting_place_id: Mapped[UUID] = mapped_column(
        ForeignKey("tse_voting_places.id", ondelete="CASCADE"),
        nullable=False,
    )

    votes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # {"<NR_SECAO>": votos} das secoes DESTE local em que o candidato teve voto.
    # A soma dos valores e `votes`. O numero da secao so e unico dentro da
    # ZONA, e a zona esta no local (tse_voting_places.zone) — por isso so se
    # grava aqui quando o local tem zona. Nulo = sem detalhe carregado.
    sections: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)

    __table_args__ = (
        # UNIQUE (candidate, local) — agregado por local
        Index(
            "ix_tse_section_votes_unique",
            "candidate_id", "voting_place_id",
            unique=True,
        ),
        # Para "votos por bairro do candidato X" — escaneamos por candidate
        Index("ix_tse_section_votes_candidate", "candidate_id"),
        # Para "top candidatos no bairro Y" (futuro) — escaneamos por place
        Index("ix_tse_section_votes_place_votes", "voting_place_id", "votes"),
    )
