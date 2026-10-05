"""Voto do SEGUNDO TURNO, por municipio.

POR QUE UMA TABELA SEPARADA, e nao uma coluna `round` em tse_vote_results:

A chave de tse_vote_results e (candidato, municipio), sem turno. O importador
DESCARTA toda linha de NR_TURNO=2 justamente por isso — somar os dois turnos no
mesmo registro faria Lula 2022 aparecer com 117 milhoes de votos (57 do 1o + 60
do 2o) em vez de 57. O comentario esta em utils/tse_sync.py, na acumulacao.

Consequencia pratica: hoje, no dia do 2o turno, o sistema importaria o arquivo e
jogaria fora cada voto dele.

Para consertar havia dois caminhos:

  (a) acrescentar `round` a tse_vote_results — 23,8 milhoes de linhas, 5,3 GB, e
      auditar as ~20 consultas que hoje somam voto sem filtrar turno. Uma que
      escape passa a somar os dois turnos e mostra numero inflado ao cliente.

  (b) tabela propria — aditivo, nenhuma linha existente muda, nenhuma consulta
      atual muda de comportamento, e o volume e minusculo: em 2024 o pais
      inteiro teve 95 candidaturas em 2o turno.

Escolhemos (b). Menos elegante no diagrama, muito mais seguro perto de uma
eleicao: quem nao sabe desta tabela continua vendo exatamente o que via.
"""
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TseRunoffVote(Base, TimestampMixin):
    __tablename__ = "tse_runoff_votes"

    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("tse_candidates.id", ondelete="CASCADE"), nullable=False,
    )

    municipality_id: Mapped[UUID] = mapped_column(
        ForeignKey("tse_municipalities.id", ondelete="CASCADE"), nullable=False,
    )

    votes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        # Uma linha por candidato x municipio. O turno e implicito (sempre 2):
        # nao existe 3o turno no Brasil, entao uma coluna de turno aqui so
        # ocuparia espaco e conviteria a confusao.
        Index(
            "ix_tse_runoff_votes_unique",
            "candidate_id", "municipality_id",
            unique=True,
        ),
        Index("ix_tse_runoff_votes_municipality", "municipality_id", "votes"),
    )
