"""
TseVotingPlace — local fisico de votacao do TSE (escola/igreja/clube),
com bairro, endereco e lat/lng. Cada local hospeda multiplas secoes
eleitorais.

Fonte: `eleitorado_local_votacao_2024.zip` (~44MB) — un ico dataset
nacional. Importer dedup por (municipality_id, local_code).
"""
from uuid import UUID

from sqlalchemy import Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TseVotingPlace(Base, TimestampMixin):
    __tablename__ = "tse_voting_places"

    # Ano da eleição a que estes locais pertencem (locais mudam entre pleitos).
    # Default 2024 (era o único ano antes da dimensão de ano).
    year: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2024, server_default="2024", index=True
    )

    # NR_ZONA — a zona eleitoral. Faz parte da IDENTIDADE do local: no TSE o
    # NR_LOCAL_VOTACAO so e unico DENTRO da zona, entao sem esta coluna o
    # "local 12" da 1a zona e o "local 12" da 5a viram a mesma linha, e o
    # bairro de um deles leva os votos de todos. Media do Rio antes do
    # conserto: 163 locais para uma cidade de mais de 1.400, um deles com
    # 129.241 eleitores.
    # Nulo nas linhas anteriores ao conserto (carga de ago/2026).
    zone: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # NR_LOCAL_VOTACAO no TSE — unique POR (ano, municipio, ZONA)
    local_code: Mapped[int] = mapped_column(Integer, nullable=False)

    municipality_id: Mapped[UUID] = mapped_column(
        ForeignKey("tse_municipalities.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Info descritiva
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    neighborhood: Mapped[str | None] = mapped_column(
        String(120), nullable=True, index=True,
    )

    # Coords reais do local (do proprio TSE!)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Total de eleitores aptos a votar no local (soma das secoes)
    electors_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Origem/precisao da coordenada (migration 050):
    #   'tse'       coord real do TSE
    #   'centroid'  fallback no centro do municipio (impreciso)
    #   'nominatim' recuperada via ViaCEP -> Nominatim (pipeline de enriquecimento)
    #   'unmapped'  sem coordenada (cai na lista de "Nao Mapeados")
    geo_source: Mapped[str | None] = mapped_column(String(12), nullable=True)

    __table_args__ = (
        # Unique composto: o mesmo numero existe em municipios, anos E ZONAS
        # diferentes. NULLS NOT DISTINCT preserva a garantia antiga nas linhas
        # legadas (zone nulo): sem isso o Postgres trataria cada nulo como
        # valor distinto e aceitaria duplicata onde antes barrava.
        Index(
            "ix_tse_voting_places_year_muni_zone_code",
            "year", "municipality_id", "zone", "local_code",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        # Index por bairro pra agregacao rapida
        Index("ix_tse_voting_places_muni_neighborhood", "municipality_id", "neighborhood"),
    )
