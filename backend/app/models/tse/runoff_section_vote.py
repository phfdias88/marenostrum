"""Voto do SEGUNDO TURNO por LOCAL de votacao (base da analise por bairro).

Mesmo motivo da tse_runoff_votes: o importador de secao tambem descartava tudo
que nao fosse 1o turno (`if (_i(row.get("NR_TURNO")) or 1) != 1: continue`), e a
chave de tse_section_votes e (candidato, local), sem turno.

Sem esta tabela, no 2o turno o produto perde justamente o que ele tem de mais
valioso: a leitura por bairro. Separada da tabela do 1o turno pela mesma razao —
nenhuma consulta existente muda de comportamento.

O volume e pequeno: 2o turno so existe em eleicao majoritaria e em poucas
cidades. Em 2024 foram 95 candidaturas no pais inteiro.
"""
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TseRunoffSectionVote(Base, TimestampMixin):
    __tablename__ = "tse_runoff_section_votes"

    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("tse_candidates.id", ondelete="CASCADE"), nullable=False,
    )
    voting_place_id: Mapped[UUID] = mapped_column(
        ForeignKey("tse_voting_places.id", ondelete="CASCADE"), nullable=False,
    )
    votes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index(
            "ix_tse_runoff_section_unique",
            "candidate_id", "voting_place_id", unique=True,
        ),
        Index("ix_tse_runoff_section_place", "voting_place_id", "votes"),
    )
