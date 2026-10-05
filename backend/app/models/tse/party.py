"""Partido político (TSE)."""
from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Party(Base, TimestampMixin):
    __tablename__ = "tse_parties"

    # Número do partido (legenda eleitoral, ex: 13=PT, 22=PL).
    # NÃO é único: o TSE reaproveita número (o 14 foi PTB e hoje é MISSÃO) e
    # partido troca de nome (35: PMB → DEMOCRATA). Cada linha vale a partir de
    # `valid_from`. Quem resolve "qual linha" é app/utils/partidos.py.
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Sigla (PT, PL, MDB...)
    abbreviation: Mapped[str] = mapped_column(String(20), nullable=False)
    # Nome completo
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    # Primeiro ano em que esta sigla responde pelo número. Vazio = desde sempre.
    valid_from: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_tse_parties_number", "number"),
        Index("ix_tse_parties_number_sigla", "number", "abbreviation", unique=True),
    )
