"""
Resultado de votação — quantos votos um candidato teve em um município.

Granularidade: candidato × município (agregando zonas).
Tabela GRANDE: milhões de linhas pra Brasil 2024 (~13M candidatos × munic
após filtros). Usa índices compostos pra queries comuns.
"""
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class VoteResult(Base, TimestampMixin):
    __tablename__ = "tse_vote_results"

    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("tse_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    municipality_id: Mapped[UUID] = mapped_column(
        ForeignKey("tse_municipalities.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Soma de QT_VOTOS_NOMINAIS de todas as zonas desse municipio
    votes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        # Unique candidato+municipio (agregamos zonas em 1 linha)
        Index(
            "ix_tse_vote_results_unique",
            "candidate_id", "municipality_id", unique=True,
        ),
        # Query tipica: "votos do candidato X em todos municipios"
        Index("ix_tse_vote_results_candidate", "candidate_id"),
        # Query tipica: "todos candidatos votados no municipio Y" (rank)
        Index("ix_tse_vote_results_municipality_votes", "municipality_id", "votes"),
    )
