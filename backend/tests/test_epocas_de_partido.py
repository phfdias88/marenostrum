"""
Epocas de partido no banco: criar as linhas e repontar as candidaturas antigas.

O que estes testes protegem e o que NAO pode acontecer com 280 mil linhas de
producao: candidatura mudar de NUMERO de partido, a linha de hoje virar epoca
antiga (a filiacao iria junto), o mesmo numero ficar em duas linhas no mesmo
ano, e uma segunda rodada duplicar o que a primeira criou.
"""
import pytest
from sqlalchemy.exc import IntegrityError

from app.models.tse import Candidate, Election, Municipality, Party
from app.models.tse.party_membership import PartyMembership
from app.services import epocas_de_partido as epocas
from app.utils.partidos import IndiceDePartidos, partido_atual


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _banco_de_hoje(db):
    """Uma linha por numero, com o nome de hoje — como a producao estava."""
    partidos = {
        13: Party(number=13, abbreviation="PT", name="Partido dos Trabalhadores"),
        22: Party(number=22, abbreviation="PL", name="Partido Liberal"),
        25: Party(number=25, abbreviation="PRD", name="Partido Renovação Democrática"),
        44: Party(number=44, abbreviation="UNIÃO", name="União Brasil"),
        20: Party(number=20, abbreviation="PODE", name="Podemos"),
    }
    eleicoes = {
        ano: Election(tse_code=ano * 10, year=ano, round=1, name=f"Eleicao {ano}")
        for ano in (2002, 2006, 2010, 2016, 2018, 2020, 2022, 2024, 2026)
    }
    db.add_all([*partidos.values(), *eleicoes.values()])
    db.flush()

    sq = iter(range(1, 10_000))

    def cand(numero, ano, votos, situacao=None):
        c = Candidate(
            election_id=eleicoes[ano].id, party_id=partidos[numero].id,
            sq_candidato=next(sq), number=numero * 100, name=f"C{numero}-{ano}",
            urn_name=f"C{numero}-{ano}", office_code=6, office_name="DEPUTADO FEDERAL",
            state="RJ", total_votes=votos, result_status=situacao,
        )
        db.add(c)
        return c

    # 22: PL (2002, 2006), PR (2010-2018), PL de novo (2022 em diante)
    for ano in (2002, 2006, 2010, 2016, 2018, 2022, 2026):
        cand(22, ano, 100 + ano, "ELEITO" if ano == 2016 else None)
        cand(22, ano, 7)
    # 25: PFL (2002), DEM (2016, 2020), PRD (2024, 2026)
    for ano in (2002, 2016, 2020, 2024, 2026):
        cand(25, ano, 50 + ano, "ELEITO")
    # 44: PRP (2018); UNIAO desde 2019 — o 2020 e de suplementar feita depois
    for ano in (2018, 2020, 2022):
        cand(44, ano, 30)
    # 20: PSC ate 2022; PODE em 2024
    for ano in (2022, 2024):
        cand(20, ano, 20)
    # 13: nunca mudou de nome
    for ano in (2002, 2026):
        cand(13, ano, 10)

    cidade = Municipality(tse_code=90901, name="Cidade Nove", state="RJ")
    db.add(cidade)
    db.flush()
    # Filiacao e retrato de HOJE: esta na linha unica de cada numero.
    for numero in (22, 25):
        db.add(PartyMembership(party_id=partidos[numero].id, municipality_id=cidade.id,
                               period=202605, total=1000 + numero))
    db.commit()
    return partidos


def _siglas_por_ano(db, numero):
    linhas = db.query(Election.year, Party.abbreviation).select_from(Candidate) \
        .join(Election, Election.id == Candidate.election_id) \
        .join(Party, Party.id == Candidate.party_id) \
        .filter(Party.number == numero).distinct().all()
    return dict(sorted(linhas))


def _aplicar(db, fatia=4000):
    epocas.garantir_epocas(db)
    db.commit()
    for m in epocas.planejar(db):
        epocas.repontar(db, m, fatia=fatia)


# ------------------------------------------------------------------ o indice

def test_o_22_aceita_duas_linhas_pl_de_epocas_diferentes(db_session):
    db_session.add_all([
        Party(number=22, abbreviation="PL", name="Partido Liberal"),
        Party(number=22, abbreviation="PR", name="Partido da República", valid_from=2007),
        Party(number=22, abbreviation="PL", name="Partido Liberal", valid_from=2019),
    ])
    db_session.commit()
    assert db_session.query(Party).filter_by(number=22).count() == 3


def test_duas_linhas_sem_data_da_mesma_sigla_sao_recusadas(db_session):
    """NULL nunca e igual a NULL num indice unico comum: sem o coalesce, duas
    linhas 'desde sempre' passariam caladas e a 'de hoje' viraria sorteio."""
    db_session.add(Party(number=13, abbreviation="PT", name="PT"))
    db_session.commit()
    db_session.add(Party(number=13, abbreviation="PT", name="PT de novo"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_entre_duas_linhas_da_mesma_sigla_o_ano_decide():
    i = IndiceDePartidos()
    i.registrar(22, "PL", "pl-antigo")
    i.registrar(22, "PR", "pr", 2007)
    i.registrar(22, "PL", "pl-de-hoje", 2019)

    assert [i.achar(22, "PL", ano) for ano in (2002, 2006)] == ["pl-antigo"] * 2
    assert [i.achar(22, "PL", ano) for ano in (2020, 2026)] == ["pl-de-hoje"] * 2
    assert i.achar(22, "PR", 2012) == "pr"
    # Sem ano (o registro da eleicao mais recente, a filiacao): a de hoje.
    assert i.achar_exato(22, "PL") == i.achar(22) == "pl-de-hoje"


# --------------------------------------------------------------- as linhas

def test_a_linha_de_hoje_continua_sendo_a_de_hoje(db_session):
    """O id que existia e a epoca ATUAL: a filiacao e os candidatos de 2026
    apontam para ele. Se virasse a epoca antiga, o cartao do 25 diria 'DEM'."""
    partidos = _banco_de_hoje(db_session)
    feito = epocas.garantir_epocas(db_session)
    db_session.commit()

    do_25 = db_session.query(Party).filter_by(number=25).all()
    assert {(p.abbreviation, p.valid_from) for p in do_25} == {
        ("PFL", None), ("DEM", 2007), ("PRD", 2022),
    }
    atual = partido_atual(do_25)
    assert (atual.id, atual.abbreviation) == (partidos[25].id, "PRD")
    assert next(p.name for p in do_25 if p.abbreviation == "DEM") == "Democratas"
    # O 13 nunca mudou de nome: nem linha nova, nem data.
    assert [(p.abbreviation, p.valid_from) for p in
            db_session.query(Party).filter_by(number=13)] == [("PT", None)]
    assert {c["sigla"] for c in feito["criadas"] if c["numero"] == 22} == {"PL", "PR"}
    assert epocas.conferir(db_session) == []


def test_rodar_de_novo_nao_duplica(db_session):
    _banco_de_hoje(db_session)
    epocas.garantir_epocas(db_session)
    db_session.commit()
    antes = db_session.query(Party).count()

    feito = epocas.garantir_epocas(db_session)
    db_session.commit()

    assert (feito["criadas"], feito["datadas"]) == ([], [])
    assert db_session.query(Party).count() == antes


def test_numero_com_linha_inesperada_fica_intocado(db_session):
    """Se a linha de hoje do 25 nao for o PRD, a tabela de epocas nao vale para
    este banco: mexer seria chutar. Fica como esta, e avisa."""
    db_session.add(Party(number=25, abbreviation="OUTRO", name="Outro Partido"))
    db_session.commit()

    feito = epocas.garantir_epocas(db_session)
    db_session.commit()

    assert [(p.abbreviation, p.valid_from) for p in
            db_session.query(Party).filter_by(number=25)] == [("OUTRO", None)]
    assert any("25" in aviso for aviso in feito["ignorados"])


# --------------------------------------------------------------- o reponte

def test_cada_candidatura_vai_para_a_sigla_do_seu_ano(db_session):
    _banco_de_hoje(db_session)
    antes = epocas.retrato(db_session)

    _aplicar(db_session)

    assert _siglas_por_ano(db_session, 22) == {
        2002: "PL", 2006: "PL", 2010: "PR", 2016: "PR", 2018: "PR",
        2022: "PL", 2026: "PL",
    }
    assert _siglas_por_ano(db_session, 25) == {
        2002: "PFL", 2016: "DEM", 2020: "DEM", 2024: "PRD", 2026: "PRD",
    }
    # 2020 no 44 e eleicao suplementar feita depois de o Uniao existir.
    assert _siglas_por_ano(db_session, 44) == {2018: "PRP", 2020: "UNIÃO", 2022: "UNIÃO"}
    assert _siglas_por_ano(db_session, 20) == {2022: "PSC", 2024: "PODE"}
    assert _siglas_por_ano(db_session, 13) == {2002: "PT", 2026: "PT"}

    # A PROVA: nenhum numero mudou. Candidaturas, votos e eleitos por
    # (ano, numero) identicos, e nenhum (ano, numero) em duas linhas.
    depois = epocas.retrato(db_session)
    assert epocas.por_ano_e_numero(depois) == epocas.por_ano_e_numero(antes)
    assert epocas.anos_divididos(depois) == {}
    assert epocas.planejar(db_session) == []
    assert epocas.conferir(db_session) == []


def test_o_pl_de_2002_e_o_de_hoje_ficam_em_linhas_diferentes(db_session):
    """Mesma sigla, epocas diferentes: sem separar, o ano de 2010 (PR) ficaria
    'entre' duas metades da mesma linha e nao haveria como datar nenhuma."""
    partidos = _banco_de_hoje(db_session)
    _aplicar(db_session)

    linhas = {
        ano: pid for ano, pid in db_session.query(Election.year, Candidate.party_id)
        .join(Election, Election.id == Candidate.election_id)
        .join(Party, Party.id == Candidate.party_id)
        .filter(Party.number == 22).distinct()
    }
    assert linhas[2002] == linhas[2006] != linhas[2022]
    assert linhas[2022] == linhas[2026] == partidos[22].id      # a de hoje nao mudou de id


def test_filiacao_fica_na_linha_de_hoje(db_session):
    partidos = _banco_de_hoje(db_session)
    _aplicar(db_session)

    filiacao = {m.party_id: m.total for m in db_session.query(PartyMembership)}
    assert filiacao == {partidos[22].id: 1022, partidos[25].id: 1025}
    assert db_session.get(Party, partidos[25].id).abbreviation == "PRD"


def test_em_fatias_pequenas_e_retomando_do_meio_chega_ao_mesmo_lugar(db_session):
    """O servidor pode cair no meio. O plano e recalculado a cada rodada e so
    lista o que falta."""
    _banco_de_hoje(db_session)
    antes = epocas.por_ano_e_numero(epocas.retrato(db_session))
    epocas.garantir_epocas(db_session)
    db_session.commit()

    plano = epocas.planejar(db_session)
    total = sum(m.quantidade for m in plano)
    feitas = epocas.repontar(db_session, plano[0], fatia=1)       # so o primeiro grupo
    assert feitas == plano[0].quantidade

    resto = epocas.planejar(db_session)                            # "rodou de novo"
    assert sum(m.quantidade for m in resto) == total - feitas
    for m in resto:
        epocas.repontar(db_session, m, fatia=2)

    assert epocas.planejar(db_session) == []
    assert epocas.por_ano_e_numero(epocas.retrato(db_session)) == antes


def test_a_pausa_e_chamada_a_cada_fatia(db_session):
    _banco_de_hoje(db_session)
    epocas.garantir_epocas(db_session)
    db_session.commit()
    grupo = max(epocas.planejar(db_session), key=lambda m: m.quantidade)

    pausas: list[float] = []
    epocas.repontar(db_session, grupo, fatia=1, pausa=pausas.append)

    assert len(pausas) == grupo.quantidade and all(p >= 0 for p in pausas)


# ------------------------------------------------------------------ desfazer

def test_desfazer_volta_a_uma_linha_por_numero(db_session):
    partidos = _banco_de_hoje(db_session)
    antes = epocas.por_ano_e_numero(epocas.retrato(db_session))
    linhas_antes = db_session.query(Party).count()

    feito = epocas.garantir_epocas(db_session)
    db_session.commit()
    for m in epocas.planejar(db_session):
        epocas.repontar(db_session, m)

    r = epocas.desfazer(db_session, {"criadas": feito["criadas"], "datadas": feito["datadas"]})

    assert r["linhas_apagadas"] == len(feito["criadas"])
    assert db_session.query(Party).count() == linhas_antes
    assert {p.valid_from for p in db_session.query(Party)} == {None}
    assert _siglas_por_ano(db_session, 25) == {a: "PRD" for a in (2002, 2016, 2020, 2024, 2026)}
    assert epocas.por_ano_e_numero(epocas.retrato(db_session)) == antes
    # A filiacao nao foi junto com nenhuma linha apagada.
    assert db_session.query(PartyMembership).count() == 2
    assert db_session.get(Party, partidos[22].id).abbreviation == "PL"


# -------------------------------------------------------------------- rotas

def test_lista_de_partidos_segue_com_um_cartao_por_numero_e_ganha_as_siglas_antigas(
    client, tenant_a, db_session,
):
    _, _, token = tenant_a
    _banco_de_hoje(db_session)
    db_session.add(Party(number=17, abbreviation="PSL", name="Partido Social Liberal"))
    db_session.commit()
    _aplicar(db_session)

    r = client.get("/api/v1/tse/parties", headers=_auth(token))
    assert r.status_code == 200, r.text
    por_numero = {p["number"]: p for p in r.json()}

    assert len(por_numero) == len(r.json())                     # um cartao por numero
    assert por_numero[25]["abbreviation"] == "PRD"              # o nome de HOJE
    assert por_numero[22]["abbreviation"] == "PL"
    # O DEM e o PSL de ontem sao o Uniao de hoje: e por eles que se acha o 44.
    assert por_numero[44]["former_abbreviations"] == ["DEM", "PSL", "PFL"]
    assert por_numero[22]["former_abbreviations"] == ["PR"]
    assert por_numero[20]["former_abbreviations"] == ["PSC"]
    assert por_numero[13]["former_abbreviations"] == []
    # O PRD de hoje nao herda o DEM (que foi para o Uniao), e sim o PRP.
    assert por_numero[25]["former_abbreviations"] == ["PRP"]


def test_ranking_de_ano_antigo_mostra_a_sigla_da_epoca(client, tenant_a, db_session):
    _, _, token = tenant_a
    _banco_de_hoje(db_session)
    _aplicar(db_session)

    def siglas(ano):
        r = client.get(
            f"/api/v1/tse/stats/party-performance?year={ano}&office_code=6",
            headers=_auth(token),
        )
        assert r.status_code == 200, r.text
        return {i["party"]["number"]: (i["party"]["abbreviation"], i["lineage_number"])
                for i in r.json()["items"]}

    de_2016 = siglas(2016)
    assert de_2016[25] == ("DEM", 44)          # rotulo da epoca, linhagem do Uniao
    assert de_2016[22] == ("PR", 22)
    assert siglas(2024)[25] == ("PRD", 25)
    # Um item por numero: nenhum partido saiu repartido em duas barras.
    assert len(de_2016) == 2


# ------------------------------------------------- a prova tem de ACUSAR
#
# Os testes acima mostram que o caminho certo chega ao lugar certo. Estes
# mostram que a conferencia enxerga o caminho errado — sem eles, uma regressao
# num detector faria o "TUDO CONFERE" do script valer para qualquer coisa.

def test_a_prova_acusa_candidatura_que_mudou_de_numero(db_session):
    partidos = _banco_de_hoje(db_session)
    antes = epocas.por_ano_e_numero(epocas.retrato(db_session))
    assert antes[(2016, 22)] == (2, 2123, 1)        # candidaturas, votos, eleitos
    assert (2016, 13) not in antes

    eleito = db_session.query(Candidate).join(Election, Election.id == Candidate.election_id) \
        .filter(Candidate.party_id == partidos[22].id, Election.year == 2016,
                Candidate.result_status == "ELEITO").one()
    eleito.party_id = partidos[13].id
    db_session.commit()

    depois = epocas.por_ano_e_numero(epocas.retrato(db_session))
    assert depois[(2016, 22)] == (1, 7, 0)
    assert depois[(2016, 13)] == (1, 2116, 1)


def test_grupo_interrompido_no_meio_aparece_dividido_e_e_retomado(db_session):
    _banco_de_hoje(db_session)
    antes = epocas.por_ano_e_numero(epocas.retrato(db_session))
    epocas.garantir_epocas(db_session)
    db_session.commit()
    grupo = next(m for m in epocas.planejar(db_session) if m.quantidade > 1)

    class Caiu(Exception):
        pass

    def cair(_):
        raise Caiu

    with pytest.raises(Caiu):
        epocas.repontar(db_session, grupo, fatia=1, pausa=cair)

    assert epocas.anos_divididos(epocas.retrato(db_session)) == {
        (grupo.ano, grupo.numero): sorted([grupo.sigla_origem, grupo.sigla_destino]),
    }
    resto = epocas.planejar(db_session)
    assert [m.quantidade for m in resto
            if (m.numero, m.ano) == (grupo.numero, grupo.ano)] == [grupo.quantidade - 1]
    for m in resto:
        epocas.repontar(db_session, m)
    fim = epocas.retrato(db_session)
    assert epocas.anos_divididos(fim) == {}
    assert epocas.por_ano_e_numero(fim) == antes


def test_conferir_acusa_filiacao_em_epoca_antiga_e_linha_de_hoje_sem_data(db_session):
    partidos = _banco_de_hoje(db_session)
    epocas.garantir_epocas(db_session)
    db_session.commit()
    assert epocas.conferir(db_session) == []

    dem = db_session.query(Party).filter_by(number=25, abbreviation="DEM").one()
    db_session.query(PartyMembership).filter_by(party_id=partidos[25].id) \
        .update({"party_id": dem.id})
    db_session.commit()
    assert epocas.conferir(db_session) == [
        "25: 1 linhas de filiacao presas a epoca antiga 'DEM'"]

    # A linha de hoje do 25 perde a data (o 22 nem deixaria: o indice unico
    # recusa um segundo "PL" sem data).
    partidos[25].valid_from = None
    db_session.commit()
    problemas = [p for p in epocas.conferir(db_session) if p.startswith("25:")]
    assert any("2 linhas sem data" in p for p in problemas)
    assert any("saiu 'DEM', deveria ser 'PRD'" in p for p in problemas)


def test_candidatura_no_ano_em_que_a_epoca_comeca_fica_na_epoca_nova(db_session):
    partidos = _banco_de_hoje(db_session)
    de_2022 = db_session.query(Election).filter_by(year=2022).one()
    db_session.add(Candidate(
        election_id=de_2022.id, party_id=partidos[25].id, sq_candidato=99_001,
        number=2500, name="C25-2022", urn_name="C25-2022", office_code=6,
        office_name="DEPUTADO FEDERAL", state="RJ", total_votes=1,
    ))
    db_session.commit()

    _aplicar(db_session)

    assert _siglas_por_ano(db_session, 25)[2022] == "PRD"      # desde_atual == 2022


def test_repontar_um_grupo_nao_leva_os_anos_anteriores(db_session):
    _banco_de_hoje(db_session)
    epocas.garantir_epocas(db_session)
    db_session.commit()
    ultimo = max((m for m in epocas.planejar(db_session) if m.numero == 22),
                 key=lambda m: m.ano)

    assert epocas.repontar(db_session, ultimo) == ultimo.quantidade
    assert _siglas_por_ano(db_session, 22)[2002] == "PL"
    assert {m.ano for m in epocas.planejar(db_session) if m.numero == 22} == {
        2002, 2006, 2010, 2016,
    }


# ------------------------------------------------------ o script (main)

@pytest.fixture
def roteiro(engine, tmp_path, monkeypatch):
    """scripts/epocas_de_partido.py carregado por caminho, apontado para o
    banco do teste e com o manifesto numa pasta descartavel."""
    import importlib.util
    from pathlib import Path

    caminho = Path(__file__).resolve().parents[1] / "scripts" / "epocas_de_partido.py"
    spec = importlib.util.spec_from_file_location("roteiro_epocas", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    monkeypatch.setattr(modulo, "engine", engine)
    manifesto = tmp_path / "manifesto.json"

    def rodar(*args):
        monkeypatch.setattr(
            "sys.argv", ["-", "--manifesto", str(manifesto), "--folga", "0", *args])
        return modulo.main()

    modulo.rodar, modulo.manifesto_de_teste = rodar, manifesto
    return modulo


def test_ensaio_nao_grava_nada_nem_cria_manifesto(roteiro, db_session, capsys):
    _banco_de_hoje(db_session)
    linhas = db_session.query(Party).count()

    assert roteiro.rodar() == 0

    assert "ENSAIO" in capsys.readouterr().out
    assert db_session.query(Party).count() == linhas
    assert {p.valid_from for p in db_session.query(Party)} == {None}
    assert _siglas_por_ano(db_session, 25)[2016] == "PRD"
    assert not roteiro.manifesto_de_teste.exists()


def test_aplicar_pelo_script_confere_e_a_segunda_rodada_nao_muda_nada(
    roteiro, db_session, capsys,
):
    _banco_de_hoje(db_session)

    assert roteiro.rodar("--aplicar", "--fatia", "2") == 0
    assert "TUDO CONFERE" in capsys.readouterr().out
    assert _siglas_por_ano(db_session, 25)[2016] == "DEM"
    import json
    manifesto = json.loads(roteiro.manifesto_de_teste.read_text(encoding="utf-8"))

    assert roteiro.rodar("--aplicar") == 0
    saida = capsys.readouterr().out
    # A prova completa ja foi dada e arquivada: a rodada seguinte nao a repete
    # com um retrato tirado depois — e diz isso.
    assert "TUDO CONFERE" not in saida and "ESTRUTURA CONFERE" in saida
    assert json.loads(roteiro.manifesto_de_teste.read_text(encoding="utf-8")) == manifesto


def test_rodada_retomada_compara_com_o_retrato_da_primeira(
    roteiro, db_session, capsys, monkeypatch,
):
    """O 'antes' vivia so na memoria do processo. Numa rodada retomada ele era
    tirado do banco ja meio migrado, e a conferencia dizia TUDO CONFERE sem ter
    olhado o que a primeira rodada fez — inclusive o que ela fez de errado."""
    partidos = _banco_de_hoje(db_session)
    original = roteiro.epocas.repontar
    chamadas = []

    def repontar_e_cair(db, movimento, **kw):
        chamadas.append(movimento)
        if len(chamadas) < 3:
            return original(db, movimento, **kw)
        # Simula o pior: no meio da rodada uma candidatura vai parar em outro
        # NUMERO de partido, e o processo morre.
        errado = db.query(Candidate).join(Election, Election.id == Candidate.election_id) \
            .filter(Election.year == 2016, Candidate.result_status == "ELEITO",
                    Candidate.number == 2200).first()
        errado.party_id = partidos[13].id
        db.commit()
        raise RuntimeError("sessao caiu")

    monkeypatch.setattr(roteiro.epocas, "repontar", repontar_e_cair)
    with pytest.raises(RuntimeError):
        roteiro.rodar("--aplicar")
    monkeypatch.setattr(roteiro.epocas, "repontar", original)
    capsys.readouterr()

    assert roteiro.rodar("--aplicar") == 1                 # a retomada ACUSA
    saida = capsys.readouterr().out
    assert "DIFERENCA" in saida and "(2016, numero 22)" in saida
    assert "TUDO CONFERE" not in saida


def test_comparacao_no_ano_em_apuracao_so_exige_a_quantidade(roteiro, monkeypatch):
    """A captura grava voto e situacao de 2026 entre um retrato e o outro: ali
    a diferenca de voto nao e do reponte. Em ano fechado, qualquer diferenca e."""
    monkeypatch.setattr(roteiro.apuracao, "ANO_EM_APURACAO", 2026)
    antes = {(2026, 22): (10, 500, 1), (2016, 22): (10, 500, 1)}

    assert roteiro._comparar(antes, {(2026, 22): (10, 900, 4), (2016, 22): (10, 500, 1)}) == []
    assert len(roteiro._comparar(antes, {(2026, 22): (9, 500, 1), (2016, 22): (10, 500, 1)})) == 1
    assert len(roteiro._comparar(antes, {(2026, 22): (10, 500, 1), (2016, 22): (10, 501, 1)})) == 1
    assert len(roteiro._comparar(antes, {(2026, 22): (10, 500, 1)})) == 1


def test_desfazer_pelo_script_volta_ao_inicio(roteiro, db_session, capsys):
    _banco_de_hoje(db_session)
    antes = epocas.por_ano_e_numero(epocas.retrato(db_session))
    linhas = db_session.query(Party).count()
    assert roteiro.rodar("--aplicar") == 0

    assert roteiro.rodar("--desfazer") == 0

    db_session.expire_all()
    assert db_session.query(Party).count() == linhas
    assert {p.valid_from for p in db_session.query(Party)} == {None}
    assert epocas.por_ano_e_numero(epocas.retrato(db_session)) == antes
    assert not roteiro.manifesto_de_teste.exists()
