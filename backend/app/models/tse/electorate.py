"""Perfil do eleitorado por município (TSE — perfil_eleitorado_2024).

Uma linha por município com agregados em JSON (gênero, faixa etária, grau de
escolaridade). O CSV bruto tem milhões de linhas por município×zona×perfil;
agregamos na importação e guardamos compacto.
"""
from uuid import UUID

from sqlalchemy import JSON, BigInteger, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class MunicipalityElectorate(Base, TimestampMixin):
    __tablename__ = "tse_municipality_electorate"

    municipality_id: Mapped[UUID] = mapped_column(
        ForeignKey("tse_municipalities.id", ondelete="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(nullable=False, default=2024)

    total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # dicts {rótulo: quantidade}
    by_gender: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    by_age: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    by_education: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Estado civil e raça/cor (DS_ESTADO_CIVIL, DS_RACA_COR). Nullable: linhas
    # importadas antes do migration 044 ficam sem (cai em {} no schema).
    by_marital_status: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    by_race: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index(
            "ix_tse_muni_electorate_unique",
            "municipality_id",
            "year",
            unique=True,
        ),
    )
