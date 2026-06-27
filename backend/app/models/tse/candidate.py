"""Candidato TSE (vinculado a uma Eleição e Partido)."""
from uuid import UUID

from sqlalchemy import JSON, BigInteger, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Candidate(Base, TimestampMixin):
    __tablename__ = "tse_candidates"

    # SQ_CANDIDATO no TSE — identificador único POR pleito.
    # TSE usa IDs de 12–13 dígitos (ex: 250001595870), excede PG INTEGER (32-bit).
    sq_candidato: Mapped[int] = mapped_column(BigInteger, nullable=False)

    election_id: Mapped[UUID] = mapped_column(
        ForeignKey("tse_elections.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Número da urna (NR_CANDIDATO): 13, 22, 1313, etc
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Nome completo (NM_CANDIDATO)
    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    # Nome de urna (NM_URNA_CANDIDATO): "Lula", "Adriana K"
    urn_name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)

    party_id: Mapped[UUID] = mapped_column(
        ForeignKey("tse_parties.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # CD_CARGO (11=prefeito, 13=vereador, 1=presidente, etc)
    office_code: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # DS_CARGO ("PREFEITO", "VEREADOR")
    office_name: Mapped[str] = mapped_column(String(40), nullable=False)

    # UF onde concorreu (SG_UF)
    state: Mapped[str] = mapped_column(String(2), nullable=False, index=True)

    # CPF da PESSOA (NR_CPF_CANDIDATO, do dataset consulta_cand) — ID único entre
    # eleições/cargos/UFs. Usado pra agrupar candidaturas da mesma pessoa na
    # busca. Nullable (anos sem consulta_cand importado). NÃO exposto na API (PII).
    cpf: Mapped[str | None] = mapped_column(String(11), nullable=True)

    # Situação final (DS_SITUACAO_CANDIDATURA): DEFERIDO, INDEFERIDO, RENUNCIA
    situation: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Resultado da eleição (DS_SIT_TOT_TURNO): ELEITO, ELEITO POR QP,
    # ELEITO POR MÉDIA, NÃO ELEITO, SUPLENTE, 2º TURNO, etc.
    result_status: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Enriquecimento (datasets bem_candidato + rede_social_candidato).
    # Patrimonio total declarado (R$) e lista de URLs de redes sociais.
    assets_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    social_links: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # Total de votos nominais (soma vote_results) — pre-computado pra ranking.
    total_votes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Financas de campanha (prestacao de contas): receita e despesa totais (R$).
    revenue_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    expense_total: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        Index("ix_tse_candidates_sq", "sq_candidato", unique=True),
        # Busca tipica: por eleicao + estado + cargo
        Index(
            "ix_tse_candidates_search",
            "election_id", "state", "office_code",
        ),
        # Agrupamento por pessoa via CPF.
        Index("ix_tse_candidates_cpf", "cpf"),
    )
