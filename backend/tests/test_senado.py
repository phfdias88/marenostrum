"""
Senadores em exercicio (dados abertos do Senado) e o uso deles na bancada.

O que estes testes protegem: "no mandato" pela filiacao de HOJE so vale para a
eleicao mais recente e so para a turma que fica; lista truncada do Senado nunca
apaga a boa; e senador sem partido nao some nem se mistura com um partido.
"""
from datetime import date

import pytest

from app.models.senado import SenateMember
from app.models.tse import Election
from app.services import senado
from tests.test_eleicao_comparada import _auth, _bancada, _cenario


def _parlamentar(codigo, nome, uf, partido, fim, papel="Titular"):
    ident = {"CodigoParlamentar": str(codigo), "NomeParlamentar": nome,
             "UfParlamentar": uf}
    if partido is not None:
        ident["SiglaPartidoParlamentar"] = partido
    return {
        "IdentificacaoParlamentar": ident,
        "Mandato": {
            "UfParlamentar": uf, "DescricaoParticipacao": papel,
            "PrimeiraLegislaturaDoMandato": {"DataFim": f"{fim - 4}-01-31"},
            "SegundaLegislaturaDoMandato": {"DataFim": f"{fim}-01-31"},
        },
    }


def _resposta(parlamentares):
    return {"ListaParlamentarEmExercicio": {"Parlamentares": {"Parlamentar": parlamentares}}}


# ---------------------------------------------------------------- ler a lista

def test_le_partido_uf_papel_e_o_fim_do_mandato():
    itens = senado.ler_lista(_resposta([
        _parlamentar(5000, "Fulana", "rj", "PL", 2031),
        _parlamentar(5001, "Beltrano", "SP", None, 2027, papel="1º Suplente"),
    ]))

    assert itens[0] == {
        "code": 5000, "name": "Fulana", "state": "RJ", "party_abbr": "PL",
        "role": "Titular", "term_end": date(2031, 1, 31),
    }
    # Sem a chave de partido o senador continua na lista, como sem partido.
    assert (itens[1]["party_abbr"], itens[1]["role"]) == ("S/Partido", "1º Suplente")
    # O fim e o da SEGUNDA legislatura, nao o da primeira.
    assert itens[1]["term_end"] == date(2027, 1, 31)


def test_um_so_parlamentar_vem_como_objeto_e_ainda_e_lido():
    dado = _resposta(_parlamentar(5000, "Fulana", "RJ", "PL", 2031))
    assert [i["code"] for i in senado.ler_lista(dado)] == [5000]


def test_resposta_em_outro_formato_e_recusada():
    with pytest.raises(senado.ListaDoSenadoInvalida):
        senado.ler_lista({"erro": "fora do ar"})


# -------------------------------------------------------------------- gravar

def _lista(n, partido="PL", fim=2031):
    return [
        {"code": 6000 + i, "name": f"S{i}", "state": "RJ", "party_abbr": partido,
         "role": "Titular", "term_end": date(fim, 1, 31)}
        for i in range(n)
    ]


def test_gravar_troca_a_lista_inteira(db_session):
    senado.gravar(db_session, _lista(81, partido="PT"))
    senado.gravar(db_session, _lista(80, partido="PL"))

    partidos = {m.party_abbr for m in db_session.query(SenateMember)}
    assert partidos == {"PL"}
    assert db_session.query(SenateMember).count() == 80


def test_lista_truncada_nao_apaga_a_que_estava(db_session):
    """Resposta pela metade do Senado: gravar deixaria a bancada com 3 cadeiras."""
    senado.gravar(db_session, _lista(81))
    with pytest.raises(senado.ListaDoSenadoInvalida):
        senado.gravar(db_session, _lista(3))
    assert db_session.query(SenateMember).count() == 81


def test_no_mandato_e_so_a_turma_que_fica(db_session):
    """Depois da posse de 2027 a lista tem as turmas de 2031 e 2035: filtrar por
    mandato alem da posse traria o Senado inteiro, como se ninguem fosse novo."""
    db_session.add_all([
        SenateMember(code=1, name="SAI", state="RJ", party_abbr="PL",
                     term_end=date(2027, 1, 31)),
        SenateMember(code=2, name="FICA", state="RJ", party_abbr="PL",
                     term_end=date(2031, 1, 31)),
        SenateMember(code=3, name="ELEITO EM 2026", state="RJ", party_abbr="PL",
                     term_end=date(2035, 1, 31)),
    ])
    db_session.commit()

    assert [m.name for m in senado.no_mandato(db_session, 2026)] == ["FICA"]
    assert senado.fim_do_mandato_de_quem_fica(2026) == 2031


# ----------------------------------------------------------- uso na bancada

def _em_exercicio(db):
    db.add_all([
        # Eleito pelo PTB em 2022 (linha do cenario) e hoje no PL.
        SenateMember(code=10, name="TROCOU DE PARTIDO", state="SP", party_abbr="PL",
                     role="Titular", term_end=date(2031, 1, 31)),
        # O titular do RJ saiu; quem ocupa a cadeira e o suplente, sem partido.
        SenateMember(code=11, name="SUPLENTE RJ", state="RJ", party_abbr="S/Partido",
                     role="1º Suplente", term_end=date(2031, 1, 31)),
        # Turma que esta saindo: a vaga dela e a que a eleicao de 2026 renova.
        SenateMember(code=12, name="FIM EM 2027", state="RJ", party_abbr="PT",
                     role="Titular", term_end=date(2027, 1, 31)),
    ])
    db.commit()


def test_no_mandato_usa_o_partido_de_hoje_quando_ha_lista_do_senado(
    client, tenant_a, db_session,
):
    _, _, token = tenant_a
    _cenario(db_session)
    _em_exercicio(db_session)
    b = _bancada(client, token)

    assert (b["fonte_do_mandato"], b["mandato_ate"]) == ("senado", 2031)
    assert b["mandato_atualizado_em"]
    assert "Senado Federal" in b["observacao"]
    assert b["antes"] == 2                      # a turma de 2027 fica de fora

    antes = {c["nome"]: c for c in b["cadeiras"] if c["situacao"] == "antes"}
    assert set(antes) == {"TROCOU DE PARTIDO", "SUPLENTE RJ"}
    assert antes["SUPLENTE RJ"]["papel"] == "1º Suplente"

    # O ex-PTB conta no PL, somado ao eleito e ao que esta a frente em 2026.
    pl = next(p for p in b["partidos"] if p["sigla"] == "PL")
    assert (pl["numero"], pl["antes"], pl["eleitos"], pl["a_frente"], pl["total"]) == (
        22, 1, 1, 1, 3,
    )
    # O PRD nao herda mais o senador que saiu do PTB: so tem quem esta a frente.
    prd = next(p for p in b["partidos"] if p["sigla"] == "PRD")
    assert (prd["antes"], prd["total"]) == (0, 1)

    sem = next(p for p in b["partidos"] if p["sigla"] == "Sem partido")
    assert (sem["numero"], sem["antes"], sem["total"]) == (0, 1, 1)
    # Nada some: a soma das linhas e a soma das cadeiras.
    assert sum(p["antes"] for p in b["partidos"]) == b["antes"]


def test_carga_nova_da_lista_aparece_sem_esperar_o_cache(client, tenant_a, db_session):
    """A carga roda em outro processo e nao alcanca o cache em memoria da API.
    Sem a versao da lista na chave, a tela seguia ate 4h com a carga anterior —
    ou com os eleitos de 2022, se a primeira visita veio antes da primeira carga."""
    _, _, token = tenant_a
    _cenario(db_session)
    assert _bancada(client, token)["fonte_do_mandato"] == "tse"      # guardado

    _em_exercicio(db_session)                                         # 1a carga
    b = _bancada(client, token)
    assert b["fonte_do_mandato"] == "senado"
    assert next(p for p in b["partidos"] if p["sigla"] == "PL")["antes"] == 1

    # O senador de SP troca o PL pelo PT, e a lista e carregada de novo.
    from datetime import datetime, timedelta, timezone
    membro = db_session.query(SenateMember).filter_by(code=10).one()
    membro.party_abbr = "PT"
    membro.updated_at = datetime.now(timezone.utc) + timedelta(seconds=5)
    db_session.commit()

    b = _bancada(client, token)
    por_sigla = {p["sigla"]: p["antes"] for p in b["partidos"]}
    assert (por_sigla["PT"], por_sigla["PL"]) == (1, 0)


def test_data_da_lista_e_a_de_brasilia(db_session):
    """21h30 de Brasilia ja e o dia seguinte em UTC: a tela dizia 'lista de
    amanha'."""
    from datetime import datetime, timezone
    db_session.add(SenateMember(
        code=1, name="X", state="RJ", party_abbr="PL", term_end=date(2031, 1, 31),
        updated_at=datetime(2026, 10, 6, 0, 30, tzinfo=timezone.utc),
    ))
    db_session.commit()
    assert senado.atualizado_em(db_session) == date(2026, 10, 5)


def test_sem_lista_do_senado_vale_o_eleito_de_quatro_anos_antes(
    client, tenant_a, db_session,
):
    _, _, token = tenant_a
    _cenario(db_session)
    b = _bancada(client, token)

    assert b["fonte_do_mandato"] == "tse"
    assert b["mandato_atualizado_em"] is None
    assert {c["papel"] for c in b["cadeiras"]} == {None}


def test_lista_de_hoje_nao_e_pintada_sobre_eleicao_antiga(
    client, tenant_a, db_session,
):
    """Com 2030 no banco, 2026 deixou de ser a eleicao mais recente: a filiacao
    de hoje nao descreve mais o Senado que saiu de 2026."""
    _, _, token = tenant_a
    _cenario(db_session)
    _em_exercicio(db_session)
    db_session.add(Election(tse_code=7000, year=2030, round=1, name="Geral 2030"))
    db_session.commit()

    assert _bancada(client, token)["fonte_do_mandato"] == "tse"


def test_camara_nao_tem_fonte_de_mandato(client, tenant_a, db_session):
    _, _, token = tenant_a
    _cenario(db_session, cargo=6)
    _em_exercicio(db_session)
    r = client.get(
        "/api/v1/tse/stats/bancada?year=2026&office_code=6", headers=_auth(token),
    )
    b = r.json()
    assert (b["fonte_do_mandato"], b["mandato_ate"]) == (None, None)
