"""
/tse/stats/aggregated-votes — votos ja somados por territorio.

O escopo decide a fonte: sem municipio soma por MUNICIPIO (tse_vote_results,
2014-2024); com municipio soma por BAIRRO (secoes, 2024 Brasil + 2018/2020/2022
so RJ). Os testes fixam esse contrato porque trocar a fonte muda o significado
do numero, nao so a performance.
"""
from app.models.tse import Candidate, Election, Municipality, Party, VoteResult
from app.models.tse.section_vote import TseSectionVote
from app.models.tse.voting_place import TseVotingPlace


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _seed(db, *, year=2024, round_=1, office=13):
    """2 municipios na UF ZZ; no primeiro, 2 locais em bairros diferentes."""
    election = Election(tse_code=777, year=year, round=round_, name=f"Eleicao {year}")
    party = Party(number=88, abbreviation="PTST", name="Partido Teste")
    db.add_all([election, party])
    db.flush()

    m1 = Municipality(tse_code=70001, name="Cidade Alfa", state="ZZ")
    m2 = Municipality(tse_code=70002, name="Cidade Beta", state="ZZ")
    db.add_all([m1, m2])
    db.flush()

    cand = Candidate(
        election_id=election.id, party_id=party.id, sq_candidato=700001,
        number=88, name="CANDIDATO TESTE", urn_name="TESTE",
        office_code=office, office_name="VEREADOR", state="ZZ", total_votes=0,
    )
    db.add(cand)
    db.flush()

    # Voto por municipio: Alfa 300, Beta 120
    db.add_all([
        VoteResult(candidate_id=cand.id, municipality_id=m1.id, votes=300),
        VoteResult(candidate_id=cand.id, municipality_id=m2.id, votes=120),
    ])

    # Voto por secao dentro de Alfa: Centro 200, Praia 100 (fecha os 300)
    l1 = TseVotingPlace(year=year, local_code=1, municipality_id=m1.id,
                        name="ESCOLA CENTRO", neighborhood="CENTRO",
                        electors_total=500)
    l2 = TseVotingPlace(year=year, local_code=2, municipality_id=m1.id,
                        name="ESCOLA PRAIA", neighborhood="PRAIA",
                        electors_total=300)
    db.add_all([l1, l2])
    db.flush()
    db.add_all([
        TseSectionVote(candidate_id=cand.id, voting_place_id=l1.id, votes=200),
        TseSectionVote(candidate_id=cand.id, voting_place_id=l2.id, votes=100),
    ])
    db.commit()
    return m1, m2, cand


def test_sem_municipio_soma_por_municipio(client, tenant_a, db_session):
    _, _, token = tenant_a
    _seed(db_session)

    r = client.get(
        "/api/v1/tse/stats/aggregated-votes?uf=ZZ&year=2024&office_code=13",
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["escopo"] == "municipio"
    assert body["dados_confiaveis"] is True          # voto por municipio e exato
    assert body["total_votos"] == 420                # 300 + 120
    nomes = {i["municipio"]: i["total_votos"] for i in body["itens"]}
    assert nomes == {"Cidade Alfa": 300, "Cidade Beta": 120}
    assert all(i["bairro"] is None for i in body["itens"])


def test_com_municipio_soma_por_bairro(client, tenant_a, db_session):
    _, _, token = tenant_a
    m1, _, _ = _seed(db_session)

    r = client.get(
        f"/api/v1/tse/stats/aggregated-votes?uf=ZZ&year=2024&office_code=13"
        f"&municipality_id={m1.id}",
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["escopo"] == "bairro"
    # A quebra por bairro e aproximada enquanto o local nao carregar a zona.
    assert body["dados_confiaveis"] is False
    bairros = {i["bairro"]: i["total_votos"] for i in body["itens"]}
    assert bairros == {"CENTRO": 200, "PRAIA": 100}
    # A soma dos bairros fecha com o total do municipio.
    assert body["total_votos"] == 300


def test_ordena_do_maior_para_o_menor(client, tenant_a, db_session):
    _, _, token = tenant_a
    m1, _, _ = _seed(db_session)

    r = client.get(
        f"/api/v1/tse/stats/aggregated-votes?uf=ZZ&year=2024&office_code=13"
        f"&municipality_id={m1.id}",
        headers=_auth(token),
    )
    votos = [i["total_votos"] for i in r.json()["itens"]]
    assert votos == sorted(votos, reverse=True)


def test_ano_sem_dado_de_secao_volta_vazio_e_nao_erro(client, tenant_a, db_session):
    """2016 nao tem secao importada. Isso e ausencia de dado, nao falha."""
    _, _, token = tenant_a
    m1, _, _ = _seed(db_session, year=2016)

    r = client.get(
        f"/api/v1/tse/stats/aggregated-votes?uf=ZZ&year=2016&office_code=13"
        f"&municipality_id={m1.id}",
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["itens"] == []
    assert "2024" in body["cobertura"]      # a resposta explica o recorte


def test_finalista_de_2o_turno_nao_pode_sumir(client, tenant_a, db_session):
    """A armadilha que custou caro: no TSE, quem vai ao 2o turno fica num
    registro com round=2 carregando os votos do 1o turno. Conferido em
    producao — Sao Paulo 2024: 8 candidatos em round=1 somando 2.531.785, e
    Nunes+Boulos em round=2 com 3.577.266, que sao os votos de 1o turno deles.
    Filtrar round==1 esconderia os dois mais votados. O total tem de somar os
    dois registros."""
    _, _, token = tenant_a
    m1, m2, _ = _seed(db_session)

    # Mesmo ano e cargo, mas registrado como 2o turno, com voto no mesmo municipio.
    from app.models.tse import Candidate, Election, Party, VoteResult
    e2 = Election(tse_code=778, year=2024, round=2, name="Eleicao 2024 2T")
    db_session.add(e2)
    db_session.flush()
    partido = db_session.query(Party).filter(Party.number == 88).one()
    finalista = Candidate(
        election_id=e2.id, party_id=partido.id, sq_candidato=700099,
        number=77, name="FINALISTA", urn_name="FINALISTA",
        office_code=13, office_name="VEREADOR", state="ZZ", total_votes=0,
    )
    db_session.add(finalista)
    db_session.flush()
    db_session.add(VoteResult(candidate_id=finalista.id, municipality_id=m1.id, votes=500))
    db_session.commit()

    r = client.get(
        "/api/v1/tse/stats/aggregated-votes?uf=ZZ&year=2024&office_code=13",
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    porcidade = {i["municipio"]: i["total_votos"] for i in body["itens"]}
    # Alfa = 300 (round 1) + 500 (o finalista) = 800. Sem somar os dois
    # registros daria 300 e o finalista sumiria do painel.
    assert porcidade["Cidade Alfa"] == 800
    assert body["total_votos"] == 920


def test_municipio_inexistente_e_404(client, tenant_a, db_session):
    _, _, token = tenant_a
    _seed(db_session)

    r = client.get(
        "/api/v1/tse/stats/aggregated-votes?uf=ZZ&year=2024&office_code=13"
        "&municipality_id=00000000-0000-0000-0000-000000000000",
        headers=_auth(token),
    )
    assert r.status_code == 404, r.text


def test_chave_de_api_le_a_rota(client, tenant_a, db_session):
    """A rota nasce dentro do escopo de leitura da chave — e dado publico."""
    from tests.test_api_keys import _cria_chave

    tenant, _, _ = tenant_a
    _seed(db_session)
    raw = _cria_chave(db_session, tenant.id, raw="mn_live_agg_teste_0987654321")

    r = client.get(
        "/api/v1/tse/stats/aggregated-votes?uf=ZZ&year=2024&office_code=13",
        headers={"X-API-Key": raw},
    )
    assert r.status_code == 200, r.text
    assert r.json()["total_votos"] == 420
