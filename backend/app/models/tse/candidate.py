"""Candidato TSE (vinculado a uma Eleição e Partido)."""
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Candidate(Base, TimestampMixin):
    __tablename__ = "tse_candidates"

    # SQ_CANDIDATO no TSE — identificador único POR pleito
    sq_candidato: Mapped[int] = mapped_column(Integer, nullable=False)

    election_id: Mapped[UUID] = mapped_column(
        ForeignKey("tse_elections.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Número da urna (NR_CANDIDATO): 13, 22, 1313, etc
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Nome completo (NM_CANDIDATO)
    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    # Nome de urna (NM_URNA_CANDIDATO): "Lula", "Adriana K"
    urn_name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)

    party_id: Mapped[UUID] = mapped_column(
        ForeignKey("tse_parties.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # CD_CARGO (11=prefeito, 13=vereador, 1=presidente, etc)
    office_code: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # DS_CARGO ("PREFEITO", "VEREADOR")
    office_name: Mapped[str] = mapped_column(String(40), nullable=False)

    # UF onde concorreu (SG_UF)
    state: Mapped[str] = mapped_column(String(2), nullable=False, index=True)

    # Situação final (DS_SITUACAO_CANDIDATURA): DEFERIDO, INDEFERIDO, RENUNCIA
    situation: Mapped[str | None] = mapped_column(String(40), nullable=True)

    __table_args__ = (
        Index("ix_tse_candidates_sq", "sq_candidato", unique=True),
        # Busca tipica: por eleicao + estado + cargo
        Index(
            "ix_tse_candidates_search",
            "election_id", "state", "office_code",
        ),
    )
