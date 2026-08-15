"""
Geografia do Censo (IBGE) — uma tabela, tres granularidades.

POR QUE UMA TABELA SO (`census_geo`) E NAO UMA POR NIVEL:
a tabela ja existe em producao com ~50 colunas de indicadores (renda, raca,
saneamento, faixa etaria, PIB, IDHM...) e ~205 mil linhas. Municipio e setor
convivem nela desde o inicio, distinguidos pela coluna `level`. Area de
ponderacao entra como o terceiro valor de `level` — assim ela herda de graca
os indicadores, o endpoint de GeoJSON e a agregacao que ja existem. Uma tabela
separada obrigaria a replicar as ~50 colunas ou a fazer JOIN em todo lugar.

O acesso tipado por nivel vem da heranca single-table do SQLAlchemy: consultar
`AreaPonderacao` ja filtra `level='area_ponderacao'` sozinho, sem o chamador
precisar lembrar do filtro.

    db.query(AreaPonderacao).filter(AreaPonderacao.cd_mun == "3304557")

ATENCAO — esta tabela NAO e multi-tenant. Sao dados publicos do IBGE,
compartilhados por todos os clientes; por isso herda so de `Base`, sem
`TenantMixin`. Nao guarde aqui nada derivado do dado privado de um cliente
(ver a nota de isolamento de cache de IA no projeto).
"""
from __future__ import annotations

from enum import Enum

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, synonym

from app.models.base import Base

# JSONB em Postgres (producao), JSON generico no SQLite dos testes. Sem o
# variant, Base.metadata.create_all() quebra ("can't render JSONB") e derruba
# a suite inteira — mesmo padrao de contact.py/audit_log.py.
_JSONB = JSON().with_variant(JSONB, "postgresql")


class RegionType(str, Enum):
    """Granularidade da linha em `census_geo`.

    Os valores sao os que JA estao gravados no banco — em especial `setor`
    (nao "setor_censitario"). Renomear exigiria reescrever 205 mil linhas e
    todas as queries do controller de censo, sem ganho pro produto.
    """

    MUNICIPIO = "municipio"
    SETOR = "setor"
    AREA_PONDERACAO = "area_ponderacao"


class CensusGeo(Base):
    """Unidade geografica do Censo com seus indicadores.

    A chave natural e `cd_setor`, que guarda:
    - setor:            o codigo do setor censitario (15 digitos)
    - municipio:        "MUN" + codigo IBGE do municipio
    - area_ponderacao:  "APOND" + codigo da area

    O prefixo existe porque os tres niveis dividem o mesmo indice unico. O
    codigo "limpo" de cada nivel fica em `cd_mun` / `cd_apond`.
    """

    __tablename__ = "census_geo"

    # 20 e nao 12: "area_ponderacao" tem 15 caracteres e nao cabia no tamanho
    # original da coluna (migration 061 amplia).
    level: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RegionType.SETOR.value
    )

    # --- Identificacao ---------------------------------------------------
    cd_setor: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    cd_mun: Mapped[str | None] = mapped_column(String(7), nullable=True)
    nm_mun: Mapped[str | None] = mapped_column(String(80), nullable=True)
    cd_dist: Mapped[str | None] = mapped_column(String(12), nullable=True)
    nm_dist: Mapped[str | None] = mapped_column(String(80), nullable=True)
    nm_subdist: Mapped[str | None] = mapped_column(String(80), nullable=True)
    nm_bairro: Mapped[str | None] = mapped_column(String(160), nullable=True)
    situacao: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Area de ponderacao: nos SETORES diz a qual area aquele setor pertence
    # (e o que permite agregar setor -> area); nas linhas de nivel
    # `area_ponderacao` e o codigo da propria area.
    cd_apond: Mapped[str | None] = mapped_column(String(15), nullable=True)
    nm_apond: Mapped[str | None] = mapped_column(String(160), nullable=True)

    # --- Geometria -------------------------------------------------------
    # GeoJSON em JSONB (o banco nao tem PostGIS; o recorte espacial e feito em
    # Python com shapely no controller). NULLABLE de proposito: a carga
    # nacional traz os indicadores de todos os ~452 mil setores via CSV, e a
    # geometria — que e o que pesa em disco — entra depois, so nas UFs em uso.
    geometry: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)

    # --- Indicadores base ------------------------------------------------
    area_km2: Mapped[float | None] = mapped_column(Float, nullable=True)
    populacao: Mapped[int | None] = mapped_column(Integer, nullable=True)
    domicilios: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Datas declaradas na mao em vez de TimestampMixin: a tabela nasceu so com
    # created_at, e `updated_at` so chegou na migration 061 — como coluna
    # NULLABLE, porque preencher 205 mil linhas antigas com uma data inventada
    # seria mentir sobre quando o dado foi carregado.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=True,
    )

    # NOTA: as demais ~40 colunas de indicadores (raca_*, idade_*, dom_*,
    # renda_*, pib_*, idhm_*, ideb_*) existem na tabela e sao lidas por SQL
    # cru no controller e nos scripts de ingestao. Nao estao mapeadas aqui de
    # proposito: sao um catalogo que cresce a cada dataset novo, e mapear cada
    # uma so criaria uma segunda fonte de verdade pra manter em sincronia.
    # Quem precisa delas usa o ETL (que trabalha com nomes de coluna) ou SQL.

    __table_args__ = (
        Index("ix_census_geo_level_mun", "level", "cd_mun"),
        Index("ix_census_geo_mun", "cd_mun"),
        Index("ix_census_geo_apond", "cd_apond"),
    )

    # Heranca single-table: `level` decide a classe.
    __mapper_args__ = {
        "polymorphic_on": level,
        "polymorphic_identity": "__generico__",
    }

    def __repr__(self) -> str:  # pragma: no cover - conveniencia de debug
        return f"<CensusGeo {self.level} {self.cd_setor}>"


class Setor(CensusGeo):
    """Setor censitario — a menor unidade do Censo (~452 mil no Brasil)."""

    __mapper_args__ = {"polymorphic_identity": RegionType.SETOR.value}


class Municipio(CensusGeo):
    """Municipio (5.570 no Brasil), com indicadores agregados dos setores."""

    __mapper_args__ = {"polymorphic_identity": RegionType.MUNICIPIO.value}


class AreaPonderacao(CensusGeo):
    """Area de ponderacao — agrupamento de setores usado pelo IBGE para
    expandir a amostra do Censo.

    E o nivel onde vivem as variaveis que NAO existem por setor (renda
    detalhada, escolaridade, migracao, trabalho): por setor o IBGE so publica
    o questionario basico. Por isso ela entra no modelo agora, antes de
    existir dado carregado — o recorte precisa estar pronto quando os
    microdados da amostra forem liberados.

    Os nomes pedidos pelo produto (`codigo_ibge`, `nome`, `municipio_id`) sao
    sinonimos das colunas fisicas, entao valem tanto na leitura quanto no
    filtro: `AreaPonderacao.codigo_ibge == "3304557001"` funciona.
    """

    __mapper_args__ = {"polymorphic_identity": RegionType.AREA_PONDERACAO.value}

    codigo_ibge = synonym("cd_apond")
    nome = synonym("nm_apond")
    municipio_id = synonym("cd_mun")
