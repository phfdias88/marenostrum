"""Comparecimento, abstencao, brancos e nulos de um cargo numa UF (ou no pais).

POR QUE UMA TABELA PROPRIA: tudo o mais que guardamos do TSE e voto NOMINAL,
por candidato. Abstencao, branco e nulo nao pertencem a candidato nenhum —
nao ha onde pendura-los nas tabelas de voto.

DUAS FONTES, UMA FORMA:
  * eleicao em apuracao — o canal ao vivo do TSE traz estes numeros no mesmo
    arquivo do placar (blocos `s`, `e` e `v`); a captura regrava a cada passada;
  * eleicoes fechadas — o arquivo `detalhe_votacao_munzona` do TSE, somado por
    UF (scripts/importar_comparecimento.py).

`uf` e a sigla da UF, 'ZZ' para o exterior ou 'BR' para o pais inteiro. Quando
o pais nao tem linha propria, quem le soma as UFs (services/comparecimento.py).
"""
from sqlalchemy import BigInteger, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TseTurnout(Base, TimestampMixin):
    __tablename__ = "tse_turnout"

    year: Mapped[int] = mapped_column(Integer, nullable=False)
    round: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    office_code: Mapped[int] = mapped_column(Integer, nullable=False)
    uf: Mapped[str] = mapped_column(String(2), nullable=False)

    # Eleitores aptos a votar.
    electorate: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    turnout: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    abstention: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    valid_votes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    blank_votes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    null_votes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # Todos os votos dados ao cargo: validos + brancos + nulos + ANULADOS (voto
    # em candidato indeferido ou sub judice). E o denominador que o TSE usa
    # para o percentual de brancos e nulos.
    total_votes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Andamento da apuracao. Em eleicao fechada os dois ficam iguais (ou vazios,
    # quando a fonte nao traz secao).
    sections_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sections_counted: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index(
            "ix_tse_turnout_unique",
            "year", "round", "office_code", "uf",
            unique=True,
        ),
    )
