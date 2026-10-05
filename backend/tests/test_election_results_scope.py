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


def test_desempenho_do_partido_na_apuracao_usa_o_total_oficial(
    client, tenant_a, db_session, monkeypatch,
):
    """Na apuracao o voto por municipio so anda quando a varredura passa. Somar
    por ele mostrava o partido com o voto de horas atras ao lado de candidatos
    e eleitos atualizados. Fora da apuracao, a soma por municipio continua."""
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
    assert r.json()["items"][0]["total_votes"] == 700
