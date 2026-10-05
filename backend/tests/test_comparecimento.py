"""
Comparecimento, abstencao, brancos e nulos (/tse/stats/turnout).

Os numeros de referencia sao os oficiais do TSE para presidente, 1o turno:
2018 = 20,33% de abstencao, 2,65% de brancos, 6,14% de nulos. Se a conta daqui
nao reproduzir isso a partir dos totais, o denominador esta errado.
"""
import zipfile

from app.models.tse.turnout import TseTurnout
from app.services.comparecimento import (
    do_feed,
    gravar,
    importar_detalhe,
    resumir,
)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


PRESIDENTE_2018 = {
    "electorate": 147_306_295, "turnout": 117_364_654, "abstention": 29_941_171,
    "valid_votes": 107_050_749, "blank_votes": 3_106_937, "null_votes": 7_206_222,
    "total_votes": 117_364_654,
    "sections_total": 481_860, "sections_counted": 481_860,
}


# ------------------------------------------------------------------ a conta

def test_percentuais_reproduzem_os_oficiais_de_2018():
    r = resumir(2018, PRESIDENTE_2018)
    assert (r["pct_abstencao"], r["pct_brancos"], r["pct_nulos"]) == (20.33, 2.65, 6.14)
    assert r["parcial"] is False
    assert r["pct_secoes"] == 100.0


def test_senado_com_duas_vagas_divide_pelo_total_de_votos():
    """Cada eleitor da DOIS votos para senador. Dividir os brancos pelo
    comparecimento daria 20%; o certo, sobre os 200 votos, e 10%."""
    r = resumir(2026, {
        "electorate": 120, "turnout": 100, "abstention": 20,
        "valid_votes": 170, "blank_votes": 20, "null_votes": 10,
        "sections_total": 10, "sections_counted": 10,
    })
    assert r["pct_brancos"] == 10.0
    assert r["pct_nulos"] == 5.0


def test_voto_anulado_entra_no_denominador():
    """O defeito que a conferencia contra o TSE pegou. Com candidato sub judice,
    parte dos votos nao e valida, branca nem nula. Dividir so pela soma das
    tres deu 5,24% de brancos no RJ; o TSE, sobre o total de votos, da 5,09%."""
    numeros = {
        "electorate": 1300, "turnout": 1000, "abstention": 300,
        "valid_votes": 850, "blank_votes": 51, "null_votes": 69,
        "total_votes": 1000,          # 30 votos anulados
        "sections_total": 10, "sections_counted": 10,
    }
    r = resumir(2026, numeros)
    assert (r["pct_brancos"], r["pct_nulos"], r["anulados"]) == (5.1, 6.9, 30)

    # Sem o total (linha antiga), cai na soma — e o percentual sai maior.
    sem_total = resumir(2026, {**numeros, "total_votes": None})
    assert sem_total["pct_brancos"] == 5.26


def test_abstencao_na_apuracao_parcial_nao_usa_o_eleitorado_inteiro():
    """Com metade das secoes, o eleitorado total ainda inclui quem nao foi
    contado. Sobre ele a abstencao sairia 10%; sobre o que ja entrou, 20%."""
    r = resumir(2026, {
        "electorate": 1000, "turnout": 400, "abstention": 100,
        "valid_votes": 380, "blank_votes": 10, "null_votes": 10,
        "sections_total": 10, "sections_counted": 5,
    })
    assert r["pct_abstencao"] == 20.0
    assert r["parcial"] is True
    assert r["pct_secoes"] == 50.0


def test_sem_voto_nenhum_o_percentual_fica_vazio_e_nao_zero():
    r = resumir(2026, {c: 0 for c in PRESIDENTE_2018})
    assert r["pct_abstencao"] is None
    assert r["pct_brancos"] is None
    assert r["parcial"] is False


# --------------------------------------------------------------- canal vivo

FEED = {
    "s": {"ts": "499248", "st": "498669", "pst": "99,88"},
    "e": {"te": "158745502", "c": "125134641", "a": "33421250", "pa": "21,08"},
    "v": {"tv": "125134641", "vv": "119166140", "vb": "2299040",
          "tvn": "3669461", "vn": "3664221"},
}


def test_feed_do_tse_bate_com_os_percentuais_que_ele_mesmo_publica():
    """O arquivo traz os percentuais prontos (pa 21,08 / pvb 1,84 / ptvn 2,93).
    Recalcular a partir dos totais tem de dar o mesmo."""
    r = resumir(2026, do_feed(FEED))
    assert (r["pct_abstencao"], r["pct_brancos"], r["pct_nulos"]) == (21.08, 1.84, 2.93)
    assert r["pct_secoes"] == 99.88
    assert r["parcial"] is True


def test_nulos_do_feed_incluem_o_nulo_tecnico():
    """`tvn` e o total de nulos; `vn` deixa de fora o nulo tecnico."""
    assert do_feed(FEED)["null_votes"] == 3_669_461


def test_feed_sem_os_blocos_nao_vira_linha_de_zeros():
    assert do_feed({"carg": []}) is None
    assert do_feed({"s": {"ts": "10"}}) is None


def test_regravar_substitui_em_vez_de_somar(db_session):
    for comparecimento in (100, 250):
        gravar(db_session, ano=2026, turno=1, cargo=1, uf="br", numeros={
            **{c: 0 for c in PRESIDENTE_2018}, "turnout": comparecimento,
        })
    db_session.commit()

    linha = db_session.query(TseTurnout).one()
    assert (linha.uf, linha.turnout) == ("BR", 250)


# ------------------------------------------------------- arquivo do TSE

_CAB = ("ANO_ELEICAO;NR_TURNO;SG_UF;CD_MUNICIPIO;NR_ZONA;CD_CARGO;QT_APTOS;"
        "QT_TOTAL_SECOES;QT_COMPARECIMENTO;QT_ABSTENCOES;QT_TOTAL_VOTOS_VALIDOS;"
        "QT_VOTOS_BRANCOS;QT_TOTAL_VOTOS_NULOS;QT_VOTOS")


def _zip(tmp_path, linhas, com_estadual=False, cabecalho=_CAB):
    corpo = (cabecalho + "\n" + "\n".join(linhas) + "\n").encode("latin-1")
    caminho = tmp_path / "detalhe.zip"
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("detalhe_votacao_munzona_2022_BRASIL.csv", corpo)
        if com_estadual:
            z.writestr("detalhe_votacao_munzona_2022_RJ.csv", corpo)
    return caminho


_LINHAS = [
    # duas zonas do mesmo municipio do RJ, presidente
    "2022;1;RJ;60011;1;1;100;2;80;20;70;4;6;80",
    "2022;1;RJ;60011;2;1;200;3;150;50;140;5;5;150",
    # exterior
    "2022;1;ZZ;99999;1;1;50;1;10;40;9;1;0;10",
    # governador do RJ e 2o turno de presidente: nao podem cair na mesma soma
    "2022;1;RJ;60011;1;3;100;2;80;20;60;10;10;80",
    "2022;2;RJ;60011;1;1;100;2;90;10;85;2;3;90",
]


def test_detalhe_e_somado_por_turno_cargo_e_uf(tmp_path, db_session):
    r = importar_detalhe(db_session, _zip(tmp_path, _LINHAS), ano=2022)
    assert r["gravadas"] == 4            # RJ/pres, ZZ/pres, RJ/gov, RJ/pres 2o turno

    rj = db_session.query(TseTurnout).filter_by(
        year=2022, round=1, office_code=1, uf="RJ").one()
    assert (rj.electorate, rj.turnout, rj.abstention) == (300, 230, 70)
    assert (rj.valid_votes, rj.blank_votes, rj.null_votes) == (210, 9, 11)
    assert rj.total_votes == 230
    assert (rj.sections_total, rj.sections_counted) == (5, 5)


def test_zip_com_nacional_e_estadual_nao_conta_em_dobro(tmp_path, db_session):
    importar_detalhe(db_session, _zip(tmp_path, _LINHAS, com_estadual=True), ano=2022)
    rj = db_session.query(TseTurnout).filter_by(
        year=2022, round=1, office_code=1, uf="RJ").one()
    assert rj.turnout == 230


def test_reimportar_nao_duplica(tmp_path, db_session):
    z = _zip(tmp_path, _LINHAS)
    importar_detalhe(db_session, z, ano=2022)
    importar_detalhe(db_session, z, ano=2022)
    assert db_session.query(TseTurnout).count() == 4


def test_formato_novo_do_tse_e_recusado_em_vez_de_gravar_zero(tmp_path, db_session):
    """Se o TSE renomear uma coluna, somar o que sobrou gravaria 'zero nulos'
    com cara de dado. Melhor parar e dizer qual coluna sumiu."""
    cab = _CAB.replace("QT_TOTAL_VOTOS_NULOS", "QT_NULOS")
    try:
        importar_detalhe(db_session, _zip(tmp_path, _LINHAS, cabecalho=cab), ano=2022)
    except ValueError as exc:
        assert "QT_TOTAL_VOTOS_NULOS" in str(exc)
    else:
        raise AssertionError("deveria ter recusado o arquivo")
    assert db_session.query(TseTurnout).count() == 0


# -------------------------------------------------------------------- rota

def test_pais_sem_linha_propria_e_a_soma_das_ufs_com_o_exterior(
    client, tenant_a, db_session, tmp_path,
):
    _, _, token = tenant_a
    importar_detalhe(db_session, _zip(tmp_path, _LINHAS), ano=2022)

    r = client.get("/api/v1/tse/stats/turnout?office_code=1", headers=_auth(token))
    assert r.status_code == 200, r.text
    (ano,) = r.json()["anos"]
    assert (ano["ano"], ano["comparecimento"], ano["abstencao"]) == (2022, 240, 110)
    assert ano["eleitorado"] == 350


def test_linha_do_pais_tem_preferencia_sobre_a_soma(client, tenant_a, db_session):
    """Na apuracao o TSE publica o nacional pronto. Se as UFs tambem estiverem
    gravadas, somar por cima contaria tudo duas vezes."""
    _, _, token = tenant_a
    base = {c: 0 for c in PRESIDENTE_2018}
    gravar(db_session, ano=2026, turno=1, cargo=1, uf="BR",
           numeros={**base, "turnout": 1000, "abstention": 250})
    gravar(db_session, ano=2026, turno=1, cargo=1, uf="RJ",
           numeros={**base, "turnout": 100, "abstention": 10})
    db_session.commit()

    r = client.get("/api/v1/tse/stats/turnout?office_code=1&uf=BR", headers=_auth(token))
    (ano,) = r.json()["anos"]
    assert ano["comparecimento"] == 1000

    r = client.get("/api/v1/tse/stats/turnout?office_code=1&uf=rj", headers=_auth(token))
    (ano,) = r.json()["anos"]
    assert ano["comparecimento"] == 100


def test_serie_vem_em_ordem_de_ano_e_separa_o_turno(client, tenant_a, db_session):
    _, _, token = tenant_a
    base = {c: 0 for c in PRESIDENTE_2018}
    for ano, turno in ((2022, 1), (2018, 1), (2022, 2)):
        gravar(db_session, ano=ano, turno=turno, cargo=1, uf="BR",
               numeros={**base, "turnout": ano + turno})
    db_session.commit()

    r = client.get("/api/v1/tse/stats/turnout?office_code=1", headers=_auth(token))
    assert [a["ano"] for a in r.json()["anos"]] == [2018, 2022]
    assert r.json()["anos"][1]["comparecimento"] == 2023       # 1o turno, nao o 2o
