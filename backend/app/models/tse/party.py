"""Partido político (TSE)."""
from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Party(Base, TimestampMixin):
    __tablename__ = "tse_parties"

    # Número do partido (legenda eleitoral, ex: 13=PT, 22=PL).
    # Index unique em __table_args__ — sem index=True aqui pra evitar duplicação.
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Sigla (PT, PL, MDB...)
    abbreviation: Mapped[str] = mapped_column(String(20), nullable=False)
    # Nome completo
    name: Mapped[str] = mapped_column(String(180), nullable=False)

    __table_args__ = (
        Index("ix_tse_parties_number", "number", unique=True),
    )
