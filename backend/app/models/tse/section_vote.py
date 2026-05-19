"""
TseSectionVote — votos de UM candidato em UM local de votacao
(agregado de todas as secoes do mesmo local).

Importante: nao armazenamos por secao (NR_SECAO) porque inflaria a tabela
em ~5x sem ganho. Bairro/local sao a granularidade util para analise
politica; secao e granular demais pra UI.

Fonte: `votacao_secao_2024_<UF>.zip` — agregamos durante o import.
"""
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


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
