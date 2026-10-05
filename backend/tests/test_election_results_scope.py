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
