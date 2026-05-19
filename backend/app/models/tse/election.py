"""Eleição TSE (2024 turno 1, 2022 presidencial, etc)."""
from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Election(Base, TimestampMixin):
    __tablename__ = "tse_elections"

    # Codigo TSE (CD_ELEICAO no CSV) — identifica univocamente o pleito
    tse_code: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # 1 = primeiro turno, 2 = segundo turno, 0 = unico
    round: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # "ELEICAO MUNICIPAL 2024" — texto bruto do TSE (DS_ELEICAO)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    # ELEICAO ORDINARIA, SUPLEMENTAR, etc (NM_TIPO_ELEICAO)
    type_name: Mapped[str | None] = mapped_column(String(80), nullable=True)

    __table_args__ = (
        UniqueConstraint("tse_code", name="uq_tse_elections_tse_code"),
    )
