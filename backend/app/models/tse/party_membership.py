"""Filiação partidária por partido × município (TSE — perfil_filiacao_partidaria).

Dado PÚBLICO e AGREGADO do TSE (contagem QT_FILIADO por bucket demográfico, sem
nome/CPF/título — sem PII). Agregamos na importação pra 1 linha por
(partido, município, período), com breakdowns demográficos em JSON.

Snapshot mensal nacional: o TSE publica um único arquivo, sobrescrito todo mês
(NR_ANO_MES). Por isso a chave inclui `period` (AAAAMM), não um ano de eleição.
"""
from uuid import UUID

from sqlalchemy import JSON, BigInteger, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PartyMembership(Base, TimestampMixin):
    __tablename__ = "tse_party_membership"

    party_id: Mapped[UUID] = mapped_column(
        ForeignKey("tse_parties.id", ondelete="CASCADE"), nullable=False
    )
    municipality_id: Mapped[UUID] = mapped_column(
        ForeignKey("tse_municipalities.id", ondelete="CASCADE"), nullable=False
    )
    # AAAAMM do snapshot (ex. 202605).
    period: Mapped[int] = mapped_column(Integer, nullable=False)

    total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # dicts {rótulo: quantidade}
    by_gender: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    by_age: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    by_education: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index(
            "ix_tse_party_membership_unique",
            "party_id",
            "municipality_id",
            "period",
            unique=True,
        ),
        # Consulta típica: filiados de um partido (ranking por município).
        Index("ix_tse_party_membership_party", "party_id", "period"),
        # Consulta: todos os partidos de um município.
        Index("ix_tse_party_membership_muni", "municipality_id", "period"),
    )
