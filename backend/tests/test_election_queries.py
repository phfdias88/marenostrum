"""
/tse/elected e /tse/electorate-profile — as duas consultas pedidas pelo socio.

O teste que mais importa aqui e o do `result_status`: o TSE diz "eleito" de
tres jeitos (ELEITO, ELEITO POR QP, ELEITO POR MEDIA) e quem filtrar so pelo
primeiro perde quase todo vereador. E 'NAO ELEITO' contem 'ELEITO', entao
qualquer filtro por LIKE traz nao eleito junto.
"""
from app.models.tse import Candidate, Election, Municipality, Party, VoteResult
from app.models.tse.electorate import MunicipalityElectorate


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _seed(db):
    eleicao = Election(tse_code=555, year=2024, round=1, name="Eleicao 2024")
    partido = Party(number=45, abbreviation="XPTO", name="Partido XPTO")
    db.add_all([eleicao, partido])
    db.flush()

    m1 = Municipality(tse_code=50001, name="Cidade Norte", state="ZZ")
    m2 = Municipality(tse_code=50002, name="Cidade Sul", state="ZZ")
    db.add_all([m1, m2])
    db.flush()

    def _cand(nome, sq, status, votos, redes=None):
        c = Candidate(
            election_id=eleicao.id, party_id=partido.id, sq_candidato=sq,
            number=45, name=nome, urn_name=nome, office_code=13,
            office_name="VEREADOR", state="ZZ", result_status=status,
            total_votes=votos, social_links=redes,
        )
        db.add(c)
        db.flush()
        return c

    # Os tres jeitos de estar eleito + os dois de nao estar.
    a = _cand("ELEITA DIRETA", 500001, "ELEITO", 5000, ["https://x.com/a"])
    b = _cand("ELEITO POR QUOCIENTE", 500002, "ELEITO POR QP", 3000)
    c = _cand("ELEITO POR MEDIA", 500003, "ELEITO POR MÉDIA", 1500)
    d = _cand("NAO ELEITO", 500004, "NÃO ELEITO", 900)
    e = _cand("SUPLENTE", 500005, "SUPLENTE", 400)

    # Todos concorreram na Cidade Norte, menos o suplente (Cidade Sul).
    for cand in (a, b, c, d):
        db.add(VoteResult(candidate_id=cand.id, municipality_id=m1.id,
                          votes=cand.total_votes))
    db.add(VoteResult(candidate_id=e.id, municipality_id=m2.id, votes=400))

    db.add_all([
        MunicipalityElectorate(
            municipality_id=m1.id, year=2024, total=1000,
            by_gender={"Feminino": 520, "Masculino": 480},
            by_age={"18-24": 300, "25-34": 700},
            by_education={"Medio": 600, "Superior": 400},
            by_marital_status={"Solteiro": 700, "Casado": 300},
            by_race={"Parda": 500, "Branca": 500},
        ),
        MunicipalityElectorate(
            municipality_id=m2.id, year=2024, total=500,
            by_gender={"Feminino": 250, "Masculino": 250},
            by_age={"18-24": 200, "25-34": 300},
            by_education={"Medio": 500},
            by_marital_status={"Solteiro": 500},
            by_race={"Parda": 500},
        ),
    ])
    db.commit()
    return m1, m2


def test_eleito_cobre_os_tres_valores_do_tse(client, tenant_a, db_session):
    """O teste que justifica a funcao existir no servidor."""
    _, _, token = tenant_a
    _seed(db_session)

    r = client.get(
        "/api/v1/tse/elected?year=2024&uf=ZZ&office_code=13",
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    nomes = {i["nome"] for i in r.json()["itens"]}
    assert nomes == {"ELEITA DIRETA", "ELEITO POR QUOCIENTE", "ELEITO POR MEDIA"}


def test_nao_eleito_traz_o_resto_inclusive_suplente(client, tenant_a, db_session):
    _, _, token = tenant_a
    _seed(db_session)

    r = client.get(
        "/api/v1/tse/elected?year=2024&uf=ZZ&elected=false",
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    nomes = {i["nome"] for i in r.json()["itens"]}
    assert nomes == {"NAO ELEITO", "SUPLENTE"}


def test_filtra_por_nome_do_municipio(client, tenant_a, db_session):
    """O socio passa o NOME, nao um id — e sem se preocupar com a caixa."""
    _, _, token = tenant_a
    _seed(db_session)

    r = client.get(
        "/api/v1/tse/elected?year=2024&uf=ZZ&municipality=cidade norte",
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["municipio"] == "Cidade Norte"
    assert corpo["total"] == 3          # o suplente concorreu na outra cidade


def test_acento_nao_pode_barrar_a_busca(client, tenant_a, db_session):
    """Quem consome digita NITEROI, nao NITEROI com acento. Exigir o acento
    devolveria 404 num municipio que existe."""
    _, _, token = tenant_a
    _seed(db_session)
    m = db_session.query(Municipality).filter_by(tse_code=50001).one()
    m.name = "Cidade Norte D'Oeste"          # nome com apostrofe, sem acento
    db_session.commit()

    r = client.get(
        "/api/v1/tse/elected?year=2024&uf=ZZ&municipality=cidade norte d'oeste",
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["municipio"] == "Cidade Norte D'Oeste"


def test_municipio_inexistente_e_404(client, tenant_a, db_session):
    _, _, token = tenant_a
    _seed(db_session)

    r = client.get(
        "/api/v1/tse/elected?year=2024&uf=ZZ&municipality=CIDADE QUE NAO EXISTE",
        headers=_auth(token),
    )
    assert r.status_code == 404, r.text


def test_contatos_so_aparecem_quando_pedidos(client, tenant_a, db_session):
    _, _, token = tenant_a
    _seed(db_session)

    sem = client.get("/api/v1/tse/elected?year=2024&uf=ZZ", headers=_auth(token))
    assert all("redes_sociais" not in i for i in sem.json()["itens"])

    com = client.get(
        "/api/v1/tse/elected?year=2024&uf=ZZ&contacts=true", headers=_auth(token)
    )
    itens = {i["nome"]: i for i in com.json()["itens"]}
    assert itens["ELEITA DIRETA"]["redes_sociais"] == ["https://x.com/a"]
    # Quem nao tem rede cadastrada volta lista vazia, nao ausente.
    assert itens["ELEITO POR MEDIA"]["redes_sociais"] == []
    assert "apenas redes sociais" in com.json()["observacao"]


def test_perfil_do_eleitorado_soma_a_uf(client, tenant_a, db_session):
    _, _, token = tenant_a
    _seed(db_session)

    r = client.get(
        "/api/v1/tse/electorate-profile?year=2024&uf=ZZ", headers=_auth(token)
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["municipios_somados"] == 2
    assert corpo["total_eleitores"] == 1500
    assert corpo["sexo"] == {"Feminino": 770, "Masculino": 730}
    assert corpo["escolaridade"] == {"Medio": 1100, "Superior": 400}


def test_perfil_de_um_municipio_so(client, tenant_a, db_session):
    _, _, token = tenant_a
    _seed(db_session)

    r = client.get(
        "/api/v1/tse/electorate-profile?year=2024&uf=ZZ&municipality=CIDADE SUL",
        headers=_auth(token),
    )
    corpo = r.json()
    assert corpo["municipio"] == "Cidade Sul"
    assert corpo["total_eleitores"] == 500
    assert corpo["cor_raca"] == {"Parda": 500}


def test_avisa_quando_a_dimensao_e_quase_toda_nao_informada(client, tenant_a, db_session):
    """A armadilha nao e falta de dado, e dado dizendo "nao sei". Cor/raca e
    opcional no TSE: no RJ 2024, 12.039.902 dos 13.033.929 eleitores estao como
    "Nao informado" (92%). A dimensao SOMA o total, entao medir cobertura nao
    acusaria nada — e quem dividisse Parda pelo total leria 3,2% no lugar dos
    41,9% reais entre quem declarou."""
    _, _, token = tenant_a
    _seed(db_session)
    for linha in db_session.query(MunicipalityElectorate).all():
        linha.by_race = {"Não informado": int(linha.total * 0.9),
                         "Parda": int(linha.total * 0.1)}
    db_session.commit()

    r = client.get(
        "/api/v1/tse/electorate-profile?year=2024&uf=ZZ", headers=_auth(token)
    )
    corpo = r.json()
    assert corpo["nao_informado"]["sexo"] == 0.0          # todo mundo declarou
    assert corpo["nao_informado"]["cor_raca"] >= 0.85     # quase ninguem
    assert "cor_raca" in corpo["observacao"]
    assert "denominador" in corpo["observacao"]


def test_ano_sem_eleitorado_avisa_e_nao_quebra(client, tenant_a, db_session):
    _, _, token = tenant_a
    _seed(db_session)

    r = client.get(
        "/api/v1/tse/electorate-profile?year=2020&uf=ZZ", headers=_auth(token)
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["total_eleitores"] == 0
    assert "2024" in corpo["observacao"]


def test_chave_de_api_le_as_duas_rotas(client, tenant_a, db_session):
    from tests.test_api_keys import _cria_chave

    tenant, _, _ = tenant_a
    _seed(db_session)
    raw = _cria_chave(db_session, tenant.id, raw="mn_live_consultas_teste_12345")

    for caminho in ("/api/v1/tse/elected?year=2024&uf=ZZ",
                    "/api/v1/tse/electorate-profile?year=2024&uf=ZZ"):
        r = client.get(caminho, headers={"X-API-Key": raw})
        assert r.status_code == 200, f"{caminho}: {r.text}"
