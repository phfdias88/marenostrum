"""Município (TSE). Inclui código TSE e (futuramente) IBGE."""
from sqlalchemy import Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Municipality(Base, TimestampMixin):
    __tablename__ = "tse_municipalities"

    # Codigo TSE (CD_MUNICIPIO) — diferente do IBGE
    tse_code: Mapped[int] = mapped_column(Integer, nullable=False)
    # Nome (NM_MUNICIPIO) — pode ter acentos
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    # UF (SG_UF) — 2 letras
    state: Mapped[str] = mapped_column(String(2), nullable=False, index=True)

    # Centroide do municipio (populado one-shot via dataset publico).
    # Permite renderizar markers/heatmap por municipio no mapa.
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        # Unique composto: TSE pode ter mesmo NOME em UFs diferentes
        Index("ix_tse_municipalities_tse_code", "tse_code", unique=True),
        Index("ix_tse_municipalities_state_name", "state", "name"),
    )
