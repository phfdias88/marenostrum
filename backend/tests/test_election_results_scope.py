"""
/tse/election-results — município OPCIONAL (escopo flexível).

Pedido do PO: cargos estaduais/federais (governador, senador, deputados,
presidente) não devem exigir município; a query agrega a UF (ou o país).
Cargos municipais (prefeito/vereador) seguem exigindo a cidade na UI.
"""
import uuid

from app.models.tse import (
    Candidate,
    Election,
    Municipality,
    Party,
    VoteResult,
)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _seed_state_race(db):
    """2 municípios na mesma UF + 2 candidatos a Senador com votos em ambos."""
    election = Election(tse_code=999, year=2022, round=1, name="Geral 2022")
    party = Party(number=99, abbreviation="XPTO", name="Partido XPTO")
    db.add_all([election, party])
    db.flush()

    m1 = Municipality(tse_code=90001, name="Cidade Um", state="ZZ")
    m2 = Municipality(tse_code=90002, name="Cidade Dois", state="ZZ")
    db.add_all([m1, m2])
    db.flush()

    def _cand(name, sq):
        c = Candidate(
            election_id=election.id, party_id=party.id, sq_candidato=sq,
            number=99, name=name, urn_name=name, office_code=5,
            office_name="SENADOR", state="ZZ", total_votes=0,
        )
        db.add(c)
        db.flush()
        return c

    a = _cand("CANDIDATO A", 900001)
    b = _cand("CANDIDATO B", 900002)
    # A: 100 + 50 = 150 | B: 10 + 5 = 15
    db.add_all([
        VoteResult(candidate_id=a.id, municipality_id=m1.id, votes=100),
        VoteResult(candidate_id=a.id, municipality_id=m2.id, votes=50),
        VoteResult(candidate_id=b.id, municipality_id=m1.id, votes=10),
        VoteResult(candidate_id=b.id, municipality_id=m2.id, votes=5),
    ])
    a.total_votes = 150
    b.total_votes = 15
    db.commit()
    return m1, m2, a, b


def test_state_scope_without_municipality(client, tenant_a, db_session):
    _, _, token = tenant_a
    m1, _, a, b = _seed_state_race(db_session)

    # SEM municipality_id → agrega a UF inteira.
    r = client.get(
        "/api/v1/tse/election-results?year=2022&office_code=5&state=ZZ",
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scope"] == "state"
    assert body["municipality"] is None
    assert body["state"] == "ZZ"
    votes = {i["candidate"]["name"]: i["votes"] for i in body["results"]}
    assert votes["CANDIDATO A"] == 150  # 100 + 50 (soma dos 2 municípios)
    assert votes["CANDIDATO B"] == 15
    assert body["total_votes"] == 165


def test_municipality_scope_narrows_result(client, tenant_a, db_session):
    _, _, token = tenant_a
    m1, _, _, _ = _seed_state_race(db_session)

    # COM municipality_id → afunila pra cidade (só os votos dela).
    r = client.get(
        f"/api/v1/tse/election-results?year=2022&office_code=5&municipality_id={m1.id}",
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scope"] == "municipality"
    assert body["municipality"]["name"] == "Cidade Um"
    votes = {i["candidate"]["name"]: i["votes"] for i in body["results"]}
    assert votes["CANDIDATO A"] == 100  # só a Cidade Um
    assert votes["CANDIDATO B"] == 10
    assert body["total_votes"] == 110


def test_presidente_no_pais_usa_o_total_oficial_do_candidato(
    client, tenant_a, db_session,
):
    """Na apuracao, a soma por municipio fica atras do placar nacional e nao
    tem o voto do exterior. O total do pais e o `total_votes` do candidato."""
    _, _, token = tenant_a
    election = Election(tse_code=6257, year=2026, round=1, name="Federal 2026")
    party = Party(number=98, abbreviation="XY", name="Partido XY")
    muni = Municipality(tse_code=90101, name="Cidade Tres", state="RJ")
    db_session.add_all([election, party, muni])
    db_session.flush()
    cand = Candidate(
        election_id=election.id, party_id=party.id, sq_candidato=900101,
        number=98, name="PRESIDENCIAVEL", urn_name="PRESIDENCIAVEL",
        office_code=1, office_name="PRESIDENTE", state="BR", total_votes=1000,
    )
    db_session.add(cand)
    db_session.flush()
    db_session.add(VoteResult(candidate_id=cand.id, municipality_id=muni.id, votes=700))
    db_session.commit()

    pais = client.get(
        "/api/v1/tse/election-results?year=2026&office_code=1", headers=_auth(token),
    )
    assert pais.status_code == 200, pais.text
    assert pais.json()["results"][0]["votes"] == 1000
    assert pais.json()["total_votes"] == 1000

    # Recortado por UF continua sendo a soma dos municipios daquela UF.
    uf = client.get(
        "/api/v1/tse/election-results?year=2026&office_code=1&state=RJ",
        headers=_auth(token),
    )
    assert uf.json()["results"][0]["votes"] == 700


def test_year_and_office_are_required(client, tenant_a):
    _, _, token = tenant_a
    # Sem office_code → 422 (evita misturar cargos na mesma lista).
    r = client.get(
        "/api/v1/tse/election-results?year=2022&state=ZZ", headers=_auth(token)
    )
    assert r.status_code == 422


def test_unknown_municipality_returns_404(client, tenant_a):
    _, _, token = tenant_a
    r = client.get(
        f"/api/v1/tse/election-results?year=2022&office_code=5&municipality_id={uuid.uuid4()}",
        headers=_auth(token),
    )
    assert r.status_code == 404


def test_desempenho_do_partido_usa_o_total_oficial_do_candidato(
    client, tenant_a, db_session, monkeypatch,
):
    """Na apuracao o voto por municipio so anda quando a varredura passa. Somar
    por ele mostrava o partido com o voto de horas atras ao lado de candidatos
    e eleitos atualizados. Fora dela a soma por municipio dava o mesmo numero,
    mas custava minutos com o cache frio e derrubava o painel apos cada deploy:
    vale o total oficial sempre."""
    from app.utils import agg_cache, apuracao

    _, _, token = tenant_a
    election = Election(tse_code=6259, year=2026, round=1, name="Estaduais 2026")
    party = Party(number=97, abbreviation="XZ", name="Partido XZ")
    muni = Municipality(tse_code=90201, name="Cidade Quatro", state="RJ")
    db_session.add_all([election, party, muni])
    db_session.flush()
    cand = Candidate(
        election_id=election.id, party_id=party.id, sq_candidato=900201,
        number=97, name="GOVERNADORAVEL", urn_name="GOVERNADORAVEL",
        office_code=3, office_name="GOVERNADOR", state="RJ", total_votes=1000,
    )
    db_session.add(cand)
    db_session.flush()
    db_session.add(VoteResult(candidate_id=cand.id, municipality_id=muni.id, votes=700))
    db_session.commit()

    url = "/api/v1/tse/stats/party-performance?year=2026&office_code=3"

    monkeypatch.setattr(apuracao, "ANO_EM_APURACAO", 2026)
    r = client.get(url, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["total_votes"] == 1000

    agg_cache.clear_agg_cache()
    monkeypatch.setattr(apuracao, "ANO_EM_APURACAO", None)
    r = client.get(url, headers=_auth(token))
    assert r.json()["items"][0]["total_votes"] == 1000


def test_desempenho_do_partido_em_ano_sem_voto_por_municipio(
    client, tenant_a, db_session,
):
    """2002 a 2012 so tem o total do candidato (nao ha voto por municipio
    carregado). Somando pelo municipio, todo partido saia com zero voto."""
    _, _, token = tenant_a
    election = Election(tse_code=200201, year=2002, round=1, name="Gerais 2002")
    party = Party(number=96, abbreviation="XW", name="Partido XW")
    db_session.add_all([election, party])
    db_session.flush()
    for sq, votos, situacao in ((1, 300, "ELEITO"), (2, 200, "NÃO ELEITO"), (3, None, None)):
        db_session.add(Candidate(
            election_id=election.id, party_id=party.id, sq_candidato=sq,
            number=9600 + sq, name=f"C{sq}", urn_name=f"C{sq}", office_code=6,
            office_name="DEPUTADO FEDERAL", state="RJ", total_votes=votos,
            result_status=situacao,
        ))
    db_session.commit()

    r = client.get(
        "/api/v1/tse/stats/party-performance?year=2002&office_code=6",
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    item = corpo["items"][0]
    # Candidato sem total (None) e sem voto por municipio conta como candidato
    # e soma zero.
    assert (item["total_votes"], item["candidates_count"], item["elected_count"]) == (500, 3, 1)
    assert (corpo["total_votes"], corpo["total_elected"]) == (500, 1)


def test_candidato_sem_total_soma_pelo_voto_por_municipio(client, tenant_a, db_session):
    """O importador consolidado cria candidato sem `total_votes`. Enquanto o
    total nao e recalculado, o voto dele tem de sair do voto por municipio —
    senao o partido aparece com eleito e zero voto."""
    _, _, token = tenant_a
    election = Election(tse_code=619, year=2024, round=1, name="Municipais 2024")
    party = Party(number=95, abbreviation="XV", name="Partido XV")
    m1 = Municipality(tse_code=90301, name="Cidade Cinco", state="RJ")
    m2 = Municipality(tse_code=90302, name="Cidade Seis", state="RJ")
    db_session.add_all([election, party, m1, m2])
    db_session.flush()
    com_total = Candidate(
        election_id=election.id, party_id=party.id, sq_candidato=1, number=95,
        name="COM TOTAL", urn_name="COM TOTAL", office_code=11, office_name="PREFEITO",
        state="RJ", total_votes=1000,
    )
    sem_total = Candidate(
        election_id=election.id, party_id=party.id, sq_candidato=2, number=95,
        name="SEM TOTAL", urn_name="SEM TOTAL", office_code=11, office_name="PREFEITO",
        state="RJ", total_votes=None, result_status="ELEITO",
    )
    db_session.add_all([com_total, sem_total])
    db_session.flush()
    db_session.add_all([
        # Quem tem total usa o total: o detalhe (aqui defasado) nao entra.
        VoteResult(candidate_id=com_total.id, municipality_id=m1.id, votes=1),
        VoteResult(candidate_id=sem_total.id, municipality_id=m1.id, votes=40),
        VoteResult(candidate_id=sem_total.id, municipality_id=m2.id, votes=2),
    ])
    db_session.commit()

    item = client.get(
        "/api/v1/tse/stats/party-performance?year=2024&office_code=11",
        headers=_auth(token),
    ).json()["items"][0]
    assert (item["total_votes"], item["elected_count"]) == (1042, 1)


def test_sumario_da_eleicao_em_apuracao_nao_congela(client, tenant_a, db_session, monkeypatch):
    """O sumario era gravado na primeira visita e nunca mais refeito: quem
    abriu a tela com a apuracao no meio ficava com aquele total para sempre."""
    from app.utils import apuracao

    _, _, token = tenant_a
    election = Election(tse_code=6257, year=2026, round=1, name="Federais 2026")
    party = Party(number=94, abbreviation="XU", name="Partido XU")
    db_session.add_all([election, party])
    db_session.flush()
    cand = Candidate(
        election_id=election.id, party_id=party.id, sq_candidato=1, number=94,
        name="PRESIDENCIAVEL", urn_name="PRESIDENCIAVEL", office_code=1,
        office_name="PRESIDENTE", state="BR", total_votes=600,
    )
    db_session.add(cand)
    db_session.commit()
    url = f"/api/v1/tse/elections/{election.id}/stats"

    monkeypatch.setattr(apuracao, "ANO_EM_APURACAO", 2026)
    assert client.get(url, headers=_auth(token)).json()["total_votes"] == 600
    cand.total_votes = 1000                       # a apuracao andou
    db_session.commit()
    assert client.get(url, headers=_auth(token)).json()["total_votes"] == 1000
    db_session.refresh(election)
    assert election.stats_total_votes is None     # nada ficou gravado

    # Eleicao fechada: ai sim guarda, e passa a responder da coluna.
    monkeypatch.setattr(apuracao, "ANO_EM_APURACAO", None)
    assert client.get(url, headers=_auth(token)).json()["total_votes"] == 1000
    db_session.refresh(election)
    assert election.stats_total_votes == 1000


def test_trajetoria_junta_por_cpf_e_por_nome_sem_fundir_homonimo(client, tenant_a, db_session):
    """A mesma pessoa por CPF (mesmo trocando de UF e cargo) e, nos anos sem
    CPF, por nome civil + UF. O homonimo de outra UF fica de fora."""
    _, _, token = tenant_a
    e18 = Election(tse_code=297, year=2018, round=1, name="Gerais 2018")
    e22 = Election(tse_code=546, year=2022, round=1, name="Gerais 2022")
    e06 = Election(tse_code=2006001, year=2006, round=1, name="Gerais 2006")
    party = Party(number=93, abbreviation="XT", name="Partido XT")
    db_session.add_all([e18, e22, e06, party])
    db_session.flush()

    def cand(sq, eleicao, uf, cargo, cpf, nome="FULANA DE TAL"):
        c = Candidate(
            election_id=eleicao.id, party_id=party.id, sq_candidato=sq, number=930 + sq,
            name=nome, urn_name=nome, name_unaccent=nome.lower(), office_code=cargo,
            office_name="X", state=uf, cpf=cpf, total_votes=10 * sq,
        )
        db_session.add(c)
        return c

    base = cand(1, e22, "RJ", 6, "11122233344")
    cand(2, e18, "SP", 7, "11122233344")          # mesma pessoa, outra UF: vale o CPF
    cand(3, e06, "RJ", 7, None)                   # ano sem CPF: nome + UF
    cand(4, e06, "BA", 7, None)                   # homonimo de outra UF
    cand(5, e18, "RJ", 7, "99988877766")          # homonimo com OUTRO CPF
    db_session.commit()

    r = client.get(f"/api/v1/tse/candidates/{base.id}/trajectory", headers=_auth(token))
    assert r.status_code == 200, r.text
    itens = r.json()["items"]
    assert [(i["year"], i["state"]) for i in itens] == [(2022, "RJ"), (2018, "SP"), (2006, "RJ")]


def test_trajetoria_de_candidato_sem_cpf_usa_so_o_nome(client, tenant_a, db_session):
    """Todo candidato de 2026 nasce do registro sem CPF: a trajetoria dele sai
    por nome + UF (e era a consulta que levava 30 segundos)."""
    _, _, token = tenant_a
    e22 = Election(tse_code=546, year=2022, round=1, name="Gerais 2022")
    e26 = Election(tse_code=6259, year=2026, round=1, name="Gerais 2026")
    party = Party(number=92, abbreviation="XS", name="Partido XS")
    db_session.add_all([e22, e26, party])
    db_session.flush()
    linhas = []
    for sq, eleicao, uf, cpf in ((1, e26, "RJ", None), (2, e22, "RJ", "11122233344"),
                                 (3, e22, "SP", None)):
        c = Candidate(
            election_id=eleicao.id, party_id=party.id, sq_candidato=sq, number=920 + sq,
            name="BELTRANO SILVA", urn_name="BELTRANO", name_unaccent="beltrano silva",
            office_code=7, office_name="DEPUTADO ESTADUAL", state=uf, cpf=cpf,
        )
        db_session.add(c)
        linhas.append(c)
    db_session.commit()

    r = client.get(f"/api/v1/tse/candidates/{linhas[0].id}/trajectory", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert [(i["year"], i["state"]) for i in r.json()["items"]] == [(2026, "RJ"), (2022, "RJ")]
