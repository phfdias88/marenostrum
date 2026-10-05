"""
/tse/stats/bancada e /tse/stats/virada.

O que estes testes protegem e a HONESTIDADE do quadro na noite da apuracao:
"a frente" nunca pode virar "eleito", a Camara nunca pode somar a bancada que
sai com a que entra, e municipio sem os dois lados nao pode ser pintado como
"virou".
"""
from app.models.tse import Candidate, Election, Party
from app.services.eleicao_comparada import cruzar_vencedores, vagas_de_senador


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_senado_alterna_uma_e_duas_vagas():
    assert [vagas_de_senador(a) for a in (2010, 2014, 2018, 2022, 2026, 2030)] == [
        2, 1, 2, 1, 2, 1,
    ]


# ------------------------------------------------------------------ bancada

def _cenario(db, cargo=5):
    e22 = Election(tse_code=546, year=2022, round=1, name="Geral 2022")
    e26 = Election(tse_code=6259, year=2026, round=1, name="Geral 2026")
    pl = Party(number=22, abbreviation="PL", name="Partido Liberal")
    pt = Party(number=13, abbreviation="PT", name="Partido dos Trabalhadores")
    # O 20 era PSC em 2022; o banco guarda uma linha so, com o nome de hoje.
    pode = Party(number=20, abbreviation="PODE", name="Podemos")
    ptb = Party(number=14, abbreviation="PTB", name="Partido Trabalhista Brasileiro")
    prd = Party(number=25, abbreviation="PRD", name="Partido Renovação Democrática")
    db.add_all([e22, e26, pl, pt, pode, ptb, prd])
    db.flush()

    sq = iter(range(1, 1000))

    def cand(eleicao, partido, uf, nome, votos, situacao):
        db.add(Candidate(
            election_id=eleicao.id, party_id=partido.id, sq_candidato=next(sq),
            number=partido.number * 10, name=nome, urn_name=nome,
            office_code=cargo, office_name="X", state=uf,
            total_votes=votos, result_status=situacao,
        ))

    # 2022 — quem segue no mandato
    cand(e22, pl, "RJ", "SENADOR PL 22", 900, "ELEITO")
    cand(e22, ptb, "SP", "SENADOR PTB 22", 800, "ELEITO")
    cand(e22, pt, "RJ", "DERROTADO 22", 700, "NÃO ELEITO")

    # 2026, RJ — o TSE ja proclamou as duas vagas
    cand(e26, pl, "RJ", "ELEITO A", 500, "ELEITO")
    cand(e26, pt, "RJ", "ELEITO B", 400, "ELEITO")
    cand(e26, pode, "RJ", "PERDEU RJ", 300, "NÃO ELEITO")

    # 2026, SP — ainda sem situacao: so ha quem esta na frente
    cand(e26, pl, "SP", "FRENTE 1", 950, None)
    cand(e26, prd, "SP", "FRENTE 2", 940, None)
    cand(e26, pt, "SP", "TERCEIRO SP", 100, None)
    cand(e26, pode, "SP", "SEM VOTO", 0, None)
    db.commit()


def _bancada(client, token, cargo=5):
    r = client.get(
        f"/api/v1/tse/stats/bancada?year=2026&office_code={cargo}",
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_senado_separa_no_mandato_eleito_e_a_frente(client, tenant_a, db_session):
    _, _, token = tenant_a
    _cenario(db_session)
    b = _bancada(client, token)

    assert (b["modo"], b["ano_anterior"], b["vagas_por_uf"]) == ("soma", 2022, 2)
    assert (b["antes"], b["eleitos"], b["a_frente"]) == (2, 2, 2)
    assert b["em_disputa"] == 4                       # 2 UFs x 2 vagas
    assert b["ufs_pendentes"] == ["SP"]

    pl = next(p for p in b["partidos"] if p["sigla"] == "PL")
    assert (pl["antes"], pl["eleitos"], pl["a_frente"], pl["total"]) == (1, 1, 1, 3)


def test_a_frente_nunca_conta_como_eleito(client, tenant_a, db_session):
    """Quem lidera numa UF que o TSE nao fechou NAO e eleito. Se a tela somar os
    dois, anuncia um resultado que ainda nao existe."""
    _, _, token = tenant_a
    _cenario(db_session)
    b = _bancada(client, token)

    situacao = {c["nome"]: c["situacao"] for c in b["cadeiras"]}
    assert situacao["FRENTE 1"] == "a_frente"
    assert situacao["FRENTE 2"] == "a_frente"
    assert situacao["ELEITO A"] == "eleitos"
    # So cabem 2 vagas: o terceiro colocado e quem nao teve voto ficam fora.
    assert "TERCEIRO SP" not in situacao
    assert "SEM VOTO" not in situacao


def test_derrotado_nao_entra_nem_como_antes_nem_como_a_frente(
    client, tenant_a, db_session,
):
    """'NÃO ELEITO' contem 'ELEITO': um filtro por conter traria o derrotado."""
    _, _, token = tenant_a
    _cenario(db_session)
    nomes = {c["nome"] for c in _bancada(client, token)["cadeiras"]}
    assert "DERROTADO 22" not in nomes
    assert "PERDEU RJ" not in nomes


def test_senador_do_partido_fundido_aparece_no_sucessor(client, tenant_a, db_session):
    """O PTB virou PRD em 2023. O senador eleito pelo PTB em 2022 conta na
    bancada do PRD — junto com quem o PRD elege agora, numa linha so."""
    _, _, token = tenant_a
    _cenario(db_session)
    b = _bancada(client, token)

    siglas = [p["sigla"] for p in b["partidos"]]
    assert "PTB" not in siglas
    prd = next(p for p in b["partidos"] if p["sigla"] == "PRD")
    assert (prd["numero"], prd["antes"], prd["a_frente"], prd["total"]) == (25, 1, 1, 2)


def test_camara_nao_soma_a_bancada_que_sai(client, tenant_a, db_session):
    """Na Camara todo mundo e trocado. Somar 2022 com 2026 daria uma casa com
    o dobro de cadeiras."""
    _, _, token = tenant_a
    _cenario(db_session, cargo=6)
    b = _bancada(client, token, cargo=6)

    assert b["modo"] == "troca"
    assert b["a_frente"] == 0                 # proporcional nao se projeta
    # RJ fechou com 2 eleitos; SP ainda nao, entao vale a bancada de 2022 (1).
    assert b["em_disputa"] == 3
    pl = next(p for p in b["partidos"] if p["sigla"] == "PL")
    assert (pl["antes"], pl["eleitos"], pl["total"]) == (1, 1, 1)
    assert b["ufs_pendentes"] == ["SP"]


def test_bancada_so_existe_para_senado_e_camara(client, tenant_a, db_session):
    _, _, token = tenant_a
    r = client.get(
        "/api/v1/tse/stats/bancada?year=2026&office_code=3", headers=_auth(token),
    )
    assert r.status_code == 400, r.text


# ------------------------------------------------------------------- virada

def _venc(mid, numero, sigla, nome="X", votos=10):
    return {
        "municipality_id": mid, "municipality": f"Cidade {mid}", "state": "RJ",
        "latitude": -22.0, "longitude": -43.0, "party_number": numero,
        "party_abbr": sigla, "urn_name": nome, "votes": votos,
    }


def test_manteve_e_virou():
    r = cruzar_vencedores(
        [_venc("a", 13, "PT"), _venc("b", 13, "PT")],
        [_venc("a", 13, "PT"), _venc("b", 22, "PL")],
        2022, 2026,
    )
    assert (r["municipios"], r["viraram"], r["mantiveram"]) == (2, 1, 1)
    virou = {p["municipality_id"]: p["virou"] for p in r["pontos"]}
    assert virou == {"a": False, "b": True}


def test_troca_de_numero_do_mesmo_partido_nao_e_virada():
    """Podemos: 19 em 2022, 20 em 2026."""
    r = cruzar_vencedores(
        [_venc("a", 19, "PODE")], [_venc("a", 20, "PODE")], 2022, 2026,
    )
    assert r["viraram"] == 0


def test_numero_reaproveitado_por_outro_partido_e_virada():
    """14 era PTB, hoje e Missao. O numero e igual; o partido, nao."""
    r = cruzar_vencedores(
        [_venc("a", 14, "PTB")], [_venc("a", 14, "MISSÃO")], 2022, 2026,
    )
    assert r["viraram"] == 1
    assert r["transicoes"][0]["chave"] == "25>14"


def test_partido_fundido_para_o_sucessor_e_manutencao():
    r = cruzar_vencedores(
        [_venc("a", 14, "PTB")], [_venc("a", 25, "PRD")], 2022, 2026,
    )
    assert r["viraram"] == 0


def test_municipio_sem_um_dos_lados_fica_fora_e_e_contado():
    """Sem vencedor em 2022 nao ha o que comparar. Pinta-lo como 'virou' seria
    inventar; sumir com ele calado esconderia uma carga incompleta."""
    r = cruzar_vencedores(
        [_venc("a", 13, "PT")],
        [_venc("a", 13, "PT"), _venc("novo", 22, "PL")],
        2022, 2026,
    )
    assert r["municipios"] == 1
    assert r["sem_comparacao"] == 1
    assert [p["municipality_id"] for p in r["pontos"]] == ["a"]


def test_transicoes_vem_da_maior_para_a_menor():
    r = cruzar_vencedores(
        [_venc("a", 13, "PT"), _venc("b", 13, "PT"), _venc("c", 22, "PL")],
        [_venc("a", 22, "PL"), _venc("b", 22, "PL"), _venc("c", 22, "PL")],
        2022, 2026,
    )
    assert [(t["chave"], t["municipios"], t["virou"]) for t in r["transicoes"]] == [
        ("13>22", 2, True), ("22>22", 1, False),
    ]


def test_virada_recusa_anos_invertidos(client, tenant_a):
    _, _, token = tenant_a
    r = client.get(
        "/api/v1/tse/stats/virada?office_code=1&from_year=2026&to_year=2022",
        headers=_auth(token),
    )
    assert r.status_code == 400, r.text
