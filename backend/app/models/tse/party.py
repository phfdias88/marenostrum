"""Partido político (TSE)."""
from sqlalchemy import Index, Integer, String, text
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
        # Unico por (numero, sigla, EPOCA): o 22 tem duas linhas "PL" (a de
        # 2002-2006 e a de hoje, com o PR no meio). O coalesce faz a linha sem
        # data colidir com outra sem data — num indice simples NULL nunca e
        # igual a NULL, e duas linhas "desde sempre" passariam caladas.
        Index(
            "ix_tse_parties_number_sigla",
            "number", "abbreviation", text("coalesce(valid_from, 0)"),
            unique=True,
        ),
    )
