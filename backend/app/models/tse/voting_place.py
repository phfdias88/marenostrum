"""
TseVotingPlace — local fisico de votacao do TSE (escola/igreja/clube),
com bairro, endereco e lat/lng. Cada local hospeda multiplas secoes
eleitorais.

Fonte: `eleitorado_local_votacao_2024.zip` (~44MB) — un ico dataset
nacional. Importer dedup por (municipality_id, local_code).
"""
from uuid import UUID

from sqlalchemy import Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TseVotingPlace(Base, TimestampMixin):
    __tablename__ = "tse_voting_places"

    # NR_LOCAL_VOTACAO no TSE — unique POR municipio
    local_code: Mapped[int] = mapped_column(Integer, nullable=False)

    municipality_id: Mapped[UUID] = mapped_column(
        ForeignKey("tse_municipalities.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Info descritiva
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    neighborhood: Mapped[str | None] = mapped_column(
        String(120), nullable=True, index=True,
    )

    # Coords reais do local (do proprio TSE!)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Total de eleitores aptos a votar no local (soma das secoes)
    electors_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        # Unique composto: mesmo numero pode existir em municipios diferentes
        Index(
            "ix_tse_voting_places_muni_code",
            "municipality_id", "local_code",
            unique=True,
        ),
        # Index por bairro pra agregacao rapida
        Index("ix_tse_voting_places_muni_neighborhood", "municipality_id", "neighborhood"),
    )
