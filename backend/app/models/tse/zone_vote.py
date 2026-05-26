"""Votos de um candidato por ZONA eleitoral (TSE).

Fonte: votacao_candidato_munzona — tem NR_ZONA, que antes era agregado fora
(VoteResult guarda só por município). Esta tabela mantém a granularidade de
zona pra mostrar a distribuição dos votos do candidato entre as zonas.
"""
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class CandidateZoneVote(Base, TimestampMixin):
    __tablename__ = "tse_candidate_zone_votes"

    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("tse_candidates.id", ondelete="CASCADE"), nullable=False
    )
    municipality_id: Mapped[UUID] = mapped_column(
        ForeignKey("tse_municipalities.id", ondelete="CASCADE"), nullable=False
    )
    zone: Mapped[int] = mapped_column(Integer, nullable=False)
    votes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index(
            "ix_tse_zone_votes_unique",
            "candidate_id", "municipality_id", "zone",
            unique=True,
        ),
        # "votos por zona do candidato X" — escaneamos por candidate
        Index("ix_tse_zone_votes_candidate", "candidate_id"),
    )
