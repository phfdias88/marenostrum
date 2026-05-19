"""
VotingPlace — local de votação (escola, ginásio) com votos agregados
para o candidato do tenant.

Separado de `Contact` porque semanticamente é uma entidade diferente:
- Contact = pessoa física (eleitor, doador, etc) com phone/email
- VotingPlace = local geográfico com agregado de votos

Permite:
- Heatmap eleitoral (intensidade = votos)
- Comparação eleição-anterior vs eleição-atual (via election_year)
- Cruzar com contacts: "quantos contatos meus moram perto de seções onde
  perdi muitos votos?"
"""
from sqlalchemy import Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class VotingPlace(Base, TenantMixin, TimestampMixin):
    __tablename__ = "voting_places"

    # Nome do local fisico (ex: "Escola Municipal Coronel Corsino do Amarante")
    name: Mapped[str] = mapped_column(String(180), nullable=False)

    # Endereco
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    neighborhood: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)

    # Coordenadas (essenciais pro heatmap)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Dados eleitorais
    # votes = quantos votos o candidato/tenant teve neste local
    votes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # total_voters = eleitorado total do local (opcional — TSE publica)
    # Permite calcular % de votos: votes / total_voters
    total_voters: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Ano da eleicao (2020, 2024, 2026...) — permite comparacao historica
    election_year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Codigo do TSE (opcional, util pra cross-reference): ex "12345" + "0001"
    # Pra MVP nao usamos como unique — usuarios podem importar CSVs sem codigo.
    tse_code: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Observacoes livres
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        # Indices padrao multi-tenant (queries sempre filtram tenant_id)
        Index("ix_voting_places_tenant_id_id", "tenant_id", "id"),
        # Filtro por ano (heatmap por pleito)
        Index("ix_voting_places_tenant_year", "tenant_id", "election_year"),
        # Geo: usado pelo /heatmap endpoint pra retornar so' com coords
        Index(
            "ix_voting_places_tenant_geo",
            "tenant_id",
            "latitude",
            "longitude",
        ),
    )
