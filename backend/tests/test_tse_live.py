"""
Captura dos resultados AO VIVO do TSE.

As tres regras que estes testes protegem vieram de erros ja cometidos neste
projeto: voto somado em re-execucao, 1o e 2o turno no mesmo registro, e
importacao que termina "com sucesso" tendo gravado pela metade.

O formato do JSON aqui e o REAL — copiado do arquivo de presidente no
municipio do Rio (rj60011-c0001-e006257-u.json) em 04/10/2026.
"""
import io
import zipfile

from app.models.tse import Candidate, Election, Municipality, Party, VoteResult
from app.models.tse.runoff_vote import TseRunoffVote
from app.services.tse_live import (
    andamento,
    extrair_candidatos,
    gravar_totais_do_candidato,
    gravar_votos_do_municipio,
    importar_candidatos_do_registro,
    mapa_de_candidatos,
    url_do_arquivo,
)


def _feed(votos_a="0", votos_b="0", turno="1", pst="0,00", st_a="", e_a="n"):
    return {
        "ele": "6257", "t": turno, "tpabr": "mu", "cdabr": "60011",
        "dg": "04/10/2026", "hg": "18:30:00",
        "s": {"ts": "12635", "st": "6000", "pst": pst},
        "e": {"te": "4952612", "c": "3000000"},
        "carg": [{
            "cd": "1", "nmn": "Presidente",
            "agr": [
                {"n": "1", "nm": "PARTIDO A", "par": [{
                    "n": "22", "sg": "PA",
                    "cand": [{"n": "22", "sqcand": "280002551544",
                              "nm": "CANDIDATO A", "e": e_a, "st": st_a,
                              "vap": votos_a}],
                }]},
                {"n": "2", "nm": "PARTIDO B", "par": [{
                    "n": "13", "sg": "PB",
                    "cand": [{"n": "13", "sqcand": "280002551999",
                              "nm": "CANDIDATO B", "e": "n", "st": "",
                              "vap": votos_b}],
                }]},
            ],
        }],
    }


# ------------------------------------------------------------------ leitura

def test_url_de_municipio_e_de_uf():
    assert url_do_arquivo(2026, 6257, "RJ", 1, 60011).endswith(
        "/ele2026/6257/dados/rj/rj60011-c0001-e006257-u.json")
    assert url_do_arquivo(2026, 6259, "RJ", 3).endswith(
        "/ele2026/6259/dados/rj/rj-c0003-e006259-u.json")


def test_extrai_os_candidatos_do_aninhamento_do_tse():
    cands = {c["sqcand"]: c for c in extrair_candidatos(_feed("1234", "987"))}
    assert cands[280002551544]["votos"] == 1234
    assert cands[280002551999]["votos"] == 987


def test_voto_com_ponto_de_milhar_nao_vira_zero():
    """Se o TSE mandar '1.234.567', ler como 1 seria um desastre silencioso."""
    cands = {c["sqcand"]: c for c in extrair_candidatos(_feed("1.234.567"))}
    assert cands[280002551544]["votos"] == 1_234_567


def test_candidato_repetido_no_feed_conta_uma_vez():
    """Se o TSE mudar o aninhamento e o mesmo candidato aparecer em dois ramos,
    preferimos contar de menos a contar em dobro."""
    d = _feed("500")
    d["carg"][0]["agr"].append(d["carg"][0]["agr"][0])      # duplica o ramo
    cands = [c for c in extrair_candidatos(d) if c["sqcand"] == 280002551544]
    assert len(cands) == 1 and cands[0]["votos"] == 500


def test_andamento_le_percentual_com_virgula():
    a = andamento(_feed(pst="47,49"))
    assert a["pct_secoes"] == 47.49
    assert a["secoes_total"] == 12635
    assert a["eleitorado"] == 4952612
    assert a["turno"] == 1


def test_feed_vazio_nao_quebra():
    assert extrair_candidatos({}) == []
    assert andamento({})["pct_secoes"] == 0.0


# ----------------------------------------------------------------- gravacao

def _cenario(db):
    e = Election(tse_code=6257, year=2026, round=1, name="Federal 2026")
    p = Party(number=22, abbreviation="PA", name="Partido A")
    db.add_all([e, p])
    db.flush()
    m = Municipality(tse_code=60011, name="Rio de Janeiro", state="RJ")
    db.add(m)
    db.flush()
    for sq, nome in ((280002551544, "A"), (280002551999, "B")):
        db.add(Candidate(
            election_id=e.id, party_id=p.id, sq_candidato=sq, number=22,
            name=nome, urn_name=nome, office_code=1, office_name="PRESIDENTE",
            state="BR", total_votes=0,
        ))
    db.commit()
    return m


def test_reexecutar_SUBSTITUI_e_nao_soma(db_session):
    """A regra numero um. O feed entrega o ACUMULADO e a captura roda a noite
    inteira; somar a cada passada dobraria, triplicaria..."""
    m = _cenario(db_session)
    mapa = mapa_de_candidatos(db_session, 2026)

    for votos in ("1000", "1500", "1500"):          # tres passadas na noite
        gravar_votos_do_municipio(
            db_session, candidatos_por_sq=mapa, municipio_id=m.id, turno=1,
            candidatos=extrair_candidatos(_feed(votos, "10")),
        )
        db_session.commit()

    a = mapa[280002551544]
    linha = db_session.query(VoteResult).filter_by(candidate_id=a).one()
    assert linha.votes == 1500                       # e nao 4000
    assert db_session.query(VoteResult).count() == 2  # uma linha por candidato


def test_segundo_turno_vai_para_a_tabela_propria(db_session):
    """Misturar faria o candidato aparecer com os dois turnos somados."""
    m = _cenario(db_session)
    mapa = mapa_de_candidatos(db_session, 2026)

    gravar_votos_do_municipio(
        db_session, candidatos_por_sq=mapa, municipio_id=m.id, turno=1,
        candidatos=extrair_candidatos(_feed("57000", "51000")),
    )
    gravar_votos_do_municipio(
        db_session, candidatos_por_sq=mapa, municipio_id=m.id, turno=2,
        candidatos=extrair_candidatos(_feed("60000", "58000", turno="2")),
    )
    db_session.commit()

    a = mapa[280002551544]
    assert db_session.query(VoteResult).filter_by(candidate_id=a).one().votes == 57000
    assert db_session.query(TseRunoffVote).filter_by(candidate_id=a).one().votes == 60000


def test_candidato_fora_do_registro_e_contado_e_nao_engolido(db_session):
    """Sucesso silencioso e o pior resultado: quem veio no feed mas nao esta no
    nosso cadastro tem de aparecer no retorno."""
    m = _cenario(db_session)
    mapa = mapa_de_candidatos(db_session, 2026)
    del mapa[280002551999]                           # simula registro incompleto

    gravados, perdidos = gravar_votos_do_municipio(
        db_session, candidatos_por_sq=mapa, municipio_id=m.id, turno=1,
        candidatos=extrair_candidatos(_feed("100", "200")),
    )
    assert (gravados, perdidos) == (1, 1)


def test_total_e_situacao_do_candidato(db_session):
    _cenario(db_session)
    mapa = mapa_de_candidatos(db_session, 2026)

    gravar_totais_do_candidato(
        db_session, candidatos_por_sq=mapa, turno=1,
        candidatos=extrair_candidatos(_feed("57259504", "51072345",
                                            st_a="2º turno", e_a="n")),
    )
    db_session.commit()

    a = db_session.get(Candidate, mapa[280002551544])
    assert a.total_votes == 57259504
    assert a.result_status == "2º TURNO"


def test_total_do_2o_turno_nao_sobrescreve_o_do_1o(db_session):
    """`total_votes` e votacao de 1o turno em todas as telas. O 2o turno muda a
    situacao (ELEITO), nao o total exibido."""
    _cenario(db_session)
    mapa = mapa_de_candidatos(db_session, 2026)

    gravar_totais_do_candidato(
        db_session, candidatos_por_sq=mapa, turno=1,
        candidatos=extrair_candidatos(_feed("57000000")),
    )
    gravar_totais_do_candidato(
        db_session, candidatos_por_sq=mapa, turno=2,
        candidatos=extrair_candidatos(_feed("60000000", turno="2",
                                            st_a="Eleito", e_a="s")),
    )
    db_session.commit()

    a = db_session.get(Candidate, mapa[280002551544])
    assert a.total_votes == 57000000
    assert a.result_status == "ELEITO"


# ------------------------------------------------- candidatos pelo registro

def _zip_registro(tmp_path, linhas, com_estadual=False):
    cab = ("ANO_ELEICAO;NM_TIPO_ELEICAO;NR_TURNO;CD_ELEICAO;DS_ELEICAO;SG_UF;"
           "CD_CARGO;DS_CARGO;SQ_CANDIDATO;NR_CANDIDATO;NM_CANDIDATO;"
           "NM_URNA_CANDIDATO;DS_SITUACAO_CANDIDATURA;NR_PARTIDO;SG_PARTIDO;"
           "NM_PARTIDO")
    corpo = cab + "\n" + "\n".join(linhas) + "\n"
    caminho = tmp_path / "consulta_cand_2026.zip"
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("consulta_cand_2026_BRASIL.csv", corpo.encode("latin-1"))
        if com_estadual:                     # mesma embalagem do TSE em 2026
            z.writestr("consulta_cand_2026_RJ.csv", corpo.encode("latin-1"))
    return caminho


_GOV = "2026;ORDINARIA;1;6259;Estaduais 2026;RJ;3;GOVERNADOR;111;10;FULANO;FULANO;APTO;10;PX;Partido X"
_VICE = "2026;ORDINARIA;1;6259;Estaduais 2026;RJ;4;VICE-GOVERNADOR;112;10;BELTRANO;BELTRANO;APTO;10;PX;Partido X"
_PRES = "2026;ORDINARIA;1;6257;Federal 2026;BR;1;PRESIDENTE;113;22;SICRANO;SICRANO;APTO;22;PY;Partido Y"


def test_registro_cria_candidato_eleicao_e_partido(tmp_path, db_session):
    r = importar_candidatos_do_registro(
        db_session, _zip_registro(tmp_path, [_GOV, _PRES]), ano=2026)

    assert r["candidatos_criados"] == 2
    assert r["eleicoes_criadas"] == 2                # 6259 e 6257
    gov = db_session.query(Candidate).filter_by(sq_candidato=111).one()
    assert (gov.office_code, gov.state, gov.result_status) == (3, "RJ", None)
    assert db_session.query(Election).filter_by(tse_code=6257).one().year == 2026


def test_vice_e_suplente_nao_viram_candidato(tmp_path, db_session):
    """Vice e suplente estao no registro mas nao recebem voto proprio — criar
    essas linhas encheria a busca de candidatura que nunca tera votacao."""
    r = importar_candidatos_do_registro(
        db_session, _zip_registro(tmp_path, [_GOV, _VICE]), ano=2026)
    assert r["candidatos_criados"] == 1
    assert r["ignorados_vice_e_suplente"] == 1


def test_registro_e_idempotente(tmp_path, db_session):
    z = _zip_registro(tmp_path, [_GOV, _PRES])
    importar_candidatos_do_registro(db_session, z, ano=2026)
    de_novo = importar_candidatos_do_registro(db_session, z, ano=2026)
    assert de_novo["candidatos_criados"] == 0
    assert db_session.query(Candidate).count() == 2


def test_zip_com_nacional_e_estadual_nao_cria_em_dobro(tmp_path, db_session):
    """A embalagem que o TSE adotou em 2026: um CSV por UF mais o _BRASIL."""
    z = _zip_registro(tmp_path, [_GOV], com_estadual=True)
    r = importar_candidatos_do_registro(db_session, z, ano=2026)
    assert r["candidatos_criados"] == 1
    assert r["lidos"] == 1                           # leu so o nacional


# --------------------------------- convivencia com a carga consolidada
# Achado pela revisao na tarde do 1o turno: a carga consolidada apaga os votos
# do ano ANTES de ler o arquivo, e grava somando. Dois caminhos de desastre:
# rodar com o zip vazio (apaga tudo e termina "completed") e rodar junto com a
# captura ao vivo (a soma cai por cima e dobra).

import pytest

from app.models.tse.sync_job import SyncJobStatus, TseSyncJob
from app.services.tse_ingest import ArquivoSemDadosError, exigir_dados
from app.services.tse_live import consolidado_ja_entrou


def _zip(tmp_path, arquivos):
    caminho = tmp_path / "votacao_candidato_munzona_2026.zip"
    with zipfile.ZipFile(caminho, "w") as z:
        for nome, texto in arquivos.items():
            z.writestr(nome, texto.encode("latin-1"))
    return caminho


def test_zip_so_com_cabecalho_e_recusado(tmp_path):
    """O estado REAL do arquivo do TSE no dia do 1o turno de 2026: 29 CSVs com
    cabecalho e zero linhas, mais um leiame.pdf. Importar isso apagaria os votos
    capturados ao vivo."""
    z = _zip(tmp_path, {
        "v_2026_BRASIL.csv": "SQ_CANDIDATO;QT_VOTOS_NOMINAIS\n",
        "v_2026_RJ.csv": "SQ_CANDIDATO;QT_VOTOS_NOMINAIS\n",
        "leiame.pdf": "nao e csv",
    })
    with pytest.raises(ArquivoSemDadosError) as erro:
        exigir_dados(z)
    assert "Nada foi apagado" in str(erro.value)


def test_zip_com_dado_passa(tmp_path):
    z = _zip(tmp_path, {"v_2026_BRASIL.csv": "SQ;V\n111;10\n"})
    assert exigir_dados(z) == 1


def test_estadual_com_dado_mas_nacional_vazio_e_recusado(tmp_path):
    """Os importadores leem so o nacional quando ele existe. Se o TSE publicar os
    estaduais antes do nacional, dizer 'tem dado' faria o importador apagar os
    votos e ler um arquivo vazio."""
    z = _zip(tmp_path, {
        "v_2026_BRASIL.csv": "SQ;V\n",
        "v_2026_RJ.csv": "SQ;V\n111;10\n",
    })
    with pytest.raises(ArquivoSemDadosError):
        exigir_dados(z)


def _job(db, status, votos=0):
    j = TseSyncJob(dataset="candidato_munzona_2026", year=2026, status=status,
                   vote_results_imported=votos)
    db.add(j)
    db.commit()
    return j


def test_sem_carga_consolidada_a_captura_segue(db_session):
    assert consolidado_ja_entrou(db_session, 2026) is None


def test_carga_consolidada_em_andamento_segura_a_captura(db_session):
    """Escrever junto dobra voto: o importador soma por cima."""
    _job(db_session, SyncJobStatus.RUNNING)
    assert "em andamento" in consolidado_ja_entrou(db_session, 2026)


def test_numero_oficial_ja_gravado_encerra_a_captura(db_session):
    """Depois do consolidado, escrever ao vivo trocaria numero oficial por
    numero de divulgacao."""
    _job(db_session, SyncJobStatus.COMPLETED, votos=8_000_000)
    assert "oficiais" in consolidado_ja_entrou(db_session, 2026)


def test_carga_que_falhou_ou_nao_gravou_nada_nao_bloqueia(db_session):
    """Um job recusado pelo portao do arquivo vazio fica FAILED — isso nao pode
    desligar a captura ao vivo pelo resto da noite."""
    _job(db_session, SyncJobStatus.FAILED)
    _job(db_session, SyncJobStatus.COMPLETED, votos=0)
    assert consolidado_ja_entrou(db_session, 2026) is None


def test_registro_nao_grava_situacao_lixo(tmp_path, db_session):
    """O registro traz '#NE' nessa coluna no dia da eleicao, e o importador
    consolidado nunca atualiza candidato existente — ficaria para sempre."""
    linha = _GOV.replace(";APTO;", ";#NE;")
    importar_candidatos_do_registro(
        db_session, _zip_registro(tmp_path, [linha]), ano=2026)
    assert db_session.query(Candidate).one().situation is None


# ------------------------------------------- municipio que o banco nao tinha

def test_municipio_listado_pelo_tse_e_ausente_no_banco_e_criado(db_session):
    """Seis cidades do exterior de 2026 nao existiam no banco: a captura nunca
    pedia o voto delas, e 19 mil votos de presidente sumiam da soma."""
    from app.services.tse_live import criar_municipios_que_faltam, url_dos_municipios

    db_session.add(Municipality(tse_code=29254, name="ABIDJÃ", state="ZZ"))
    db_session.commit()
    config = {"abr": [
        {"cd": "zz", "mu": [{"cd": "29254", "nm": "ABIDJÃ"},
                            {"cd": "99999", "nm": "Cidade Nova"}]},
        {"cd": "rj", "mu": [{"cd": "60011", "nm": "RIO DE JANEIRO"}]},
    ]}

    assert criar_municipios_que_faltam(db_session, config, ["ZZ"]) == 1
    db_session.commit()

    novo = db_session.query(Municipality).filter_by(tse_code=99999).one()
    assert (novo.name, novo.state) == ("CIDADE NOVA", "ZZ")
    # A UF que nao foi pedida fica como estava.
    assert db_session.query(Municipality).filter_by(tse_code=60011).count() == 0
    # Rodar de novo nao duplica.
    assert criar_municipios_que_faltam(db_session, config, ["zz"]) == 0
    assert url_dos_municipios(2026, 6257).endswith(
        "/ele2026/6257/config/mun-e006257-cm.json")


def test_lista_de_municipios_em_formato_inesperado_nao_cria_nada(db_session):
    from app.services.tse_live import criar_municipios_que_faltam

    assert criar_municipios_que_faltam(db_session, {"abr": None}, ["ZZ"]) == 0
    assert criar_municipios_que_faltam(db_session, {}, ["ZZ"]) == 0
