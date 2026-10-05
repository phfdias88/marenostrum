"""
Modelagem multi-granularidade do censo (`census_geo`).

O que estes testes protegem: a tabela guarda tres niveis na MESMA tabela e o
filtro por nivel e implicito (heranca single-table). Se alguem trocar o
`polymorphic_identity` por engano, uma consulta de setor comeca a devolver
municipio — e o erro aparece como numero errado no mapa, nao como excecao.

Roda em SQLite (o harness do projeto), entao aqui nao se testa o CHECK do
`level` nem o JSONB — isso e Postgres e foi verificado direto no banco.
"""
from app.models.census import AreaPonderacao, CensusGeo, Municipio, RegionType, Setor


def _povoar(db):
    db.add_all([
        Setor(cd_setor="330455705000001", cd_mun="3304557", nm_mun="Rio de Janeiro",
              populacao=812, cd_apond="3304557001"),
        Setor(cd_setor="330455705000002", cd_mun="3304557", nm_mun="Rio de Janeiro",
              populacao=1044, cd_apond="3304557001"),
        Setor(cd_setor="355030805000001", cd_mun="3550308", nm_mun="Sao Paulo",
              populacao=530),
        Municipio(cd_setor="MUN3304557", cd_mun="3304557", nm_mun="Rio de Janeiro",
                  populacao=6211223),
        AreaPonderacao(cd_setor="APOND3304557001", cd_mun="3304557",
                       codigo_ibge="3304557001", nome="Copacabana"),
    ])
    db.commit()


def test_cada_nivel_enxerga_so_o_seu(db_session):
    """O filtro por `level` vem da classe — quem consulta nao precisa lembrar."""
    _povoar(db_session)

    assert db_session.query(Setor).count() == 3
    assert db_session.query(Municipio).count() == 1
    assert db_session.query(AreaPonderacao).count() == 1
    # A classe base enxerga tudo: e o que o ETL e os relatorios usam.
    assert db_session.query(CensusGeo).count() == 5


def test_level_e_gravado_sozinho(db_session):
    """Ninguem precisa (nem deve) escrever `level` na mao."""
    _povoar(db_session)

    assert db_session.query(Setor).first().level == RegionType.SETOR.value
    assert db_session.query(AreaPonderacao).first().level == "area_ponderacao"


def test_censusgeo_devolve_a_classe_certa_por_linha(db_session):
    """Ler pela base e receber o tipo especifico de volta."""
    _povoar(db_session)

    por_classe = {}
    for obj in db_session.query(CensusGeo).all():
        por_classe.setdefault(type(obj).__name__, 0)
        por_classe[type(obj).__name__] += 1

    assert por_classe == {"Setor": 3, "Municipio": 1, "AreaPonderacao": 1}


def test_nomes_de_negocio_da_area_de_ponderacao(db_session):
    """`codigo_ibge`/`nome`/`municipio_id` valem na leitura E no filtro."""
    _povoar(db_session)

    area = (
        db_session.query(AreaPonderacao)
        .filter(AreaPonderacao.codigo_ibge == "3304557001")
        .one()
    )
    assert area.nome == "Copacabana"
    assert area.municipio_id == "3304557"
    # sinonimo aponta pra mesma coluna fisica
    assert area.cd_apond == area.codigo_ibge


def test_agrega_setores_da_area_de_ponderacao(db_session):
    """O vinculo setor -> area e o que o produto vai usar em outubro."""
    _povoar(db_session)

    setores = (
        db_session.query(Setor).filter(Setor.cd_apond == "3304557001").all()
    )
    assert len(setores) == 2
    assert sum(s.populacao for s in setores) == 1856


def test_geometria_opcional(db_session):
    """Setor pode existir so com indicador: a carga nacional vem sem malha,
    que entra depois por UF. Se isto voltar a ser obrigatorio, a carga do
    pais inteiro para de rodar."""
    db_session.add(Setor(cd_setor="130026005000001", cd_mun="1300260", populacao=97))
    db_session.commit()

    salvo = db_session.query(Setor).filter_by(cd_setor="130026005000001").one()
    assert salvo.geometry is None
    assert salvo.populacao == 97
