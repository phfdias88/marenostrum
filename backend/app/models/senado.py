"""Senador em exercicio, com a filiacao de HOJE (fonte: dados abertos do Senado).

POR QUE EXISTE, se ja temos os eleitos do TSE: o TSE sabe por qual partido o
senador foi ELEITO, e para de saber ali. Troca de partido durante o mandato e
suplente que assumiu a cadeira so constam no Senado. Para a tela da bancada isso
muda o numero: dos 27 senadores com mandato ate 2031, o PL elegeu 8 em 2022 e
tem 9 hoje.

Nao e dado de tenant: e publico e igual para todos, como as tabelas do TSE.
"""
from datetime import date

from sqlalchemy import Date, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SenateMember(Base, TimestampMixin):
    __tablename__ = "senate_sitting_members"

    # CodigoParlamentar do Senado: identifica a PESSOA e nao muda.
    code: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    # Sigla como o Senado escreve ("PL", "UNIÃO", "S/Partido").
    party_abbr: Mapped[str] = mapped_column(String(30), nullable=False)
    # "Titular", "1º Suplente"... — quem esta no exercicio pode ser o suplente.
    role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Ultimo dia do mandato (31/01). E o que separa quem fica de quem sai.
    term_end: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (
        Index("ix_senate_sitting_members_code", "code", unique=True),
    )
