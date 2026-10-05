"""
/tse/municipalities/{id}/zones — o ano precisa filtrar de verdade.

A tabela de voto por zona nao tem coluna de ano. O endpoint recebia `year`, mas
so o usava na chave do cache: com duas eleicoes do mesmo cargo carregadas, a
zona somava as duas e o ranking misturava candidatos de anos diferentes sob o
rotulo do ano pedido.
"""
from app.models.tse import (
    Candidate,
    CandidateZoneVote,
    Election,
    Municipality,
    Party,
)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _seed(db):
    partido = Party(number=22, abbreviation="PL", name="Partido Liberal")
    muni = Municipality(tse_code=60011, name="Cidade Teste", state="RJ")
    e22 = Election(tse_code=546, year=2022, round=1, name="Geral 2022")
    e26 = Election(tse_code=6259, year=2026, round=1, name="Geral 2026")
    db.add_all([partido, muni, e22, e26])
    db.flush()

    def cand(eleicao, sq, nome, uf="RJ"):
        c = Candidate(
            election_id=eleicao.id, party_id=partido.id, sq_candidato=sq,
            number=22, name=nome, urn_name=nome, office_code=3,
            office_name="GOVERNADOR", state=uf,
        )
        db.add(c)
        db.flush()
        return c

    velho = cand(e22, 1, "GOVERNADOR DE 2022")
    novo = cand(e26, 2, "GOVERNADOR DE 2026")
    for c, votos in ((velho, 700), (novo, 300)):
        db.add(CandidateZoneVote(
            candidate_id=c.id, municipality_id=muni.id, zone=10,
            votes=votos, office_code=3,
        ))
    db.commit()
    return muni


def _zonas(client, token, muni, ano):
    r = client.get(
        f"/api/v1/tse/municipalities/{muni.id}/zones?office_code=3&year={ano}",
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    return r.json()["zones"]


def test_zona_de_um_ano_nao_soma_a_do_outro(client, tenant_a, db_session):
    _, _, token = tenant_a
    muni = _seed(db_session)

    zonas = _zonas(client, token, muni, 2026)
    assert len(zonas) == 1
    assert zonas[0]["total_votes"] == 300          # nao 1000
    nomes = [c["candidate"]["urn_name"] for c in zonas[0]["candidates"]]
    assert nomes == ["GOVERNADOR DE 2026"]

    zonas = _zonas(client, token, muni, 2022)
    assert zonas[0]["total_votes"] == 700
    assert [c["candidate"]["urn_name"] for c in zonas[0]["candidates"]] == [
        "GOVERNADOR DE 2022",
    ]


def test_ano_sem_zona_carregada_volta_vazio(client, tenant_a, db_session):
    """Antes, pedir um ano sem carga devolvia as zonas de outro ano."""
    _, _, token = tenant_a
    muni = _seed(db_session)
    assert _zonas(client, token, muni, 2018) == []
