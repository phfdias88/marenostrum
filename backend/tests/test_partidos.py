"""
Partido por epoca: o numero do TSE nao identifica o partido.

O caso que motivou tudo: em 2026 o numero 14 e do MISSAO, mas o banco so tinha
a linha do PTB (extinto em 2023). O importador achava o partido pelo numero e o
candidato a presidente do Missao saia na tela como "PTB".
"""
import zipfile

from app.models.tse import Candidate, Election, Party
from app.services.tse_live import importar_candidatos_do_registro
from app.utils.partidos import (
    IndiceDePartidos,
    normalizar_sigla,
    numero_sucessor,
    partido_atual,
    trechos_da_linhagem,
)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------------ a sigla

def test_grafias_diferentes_da_mesma_sigla_sao_iguais():
    """O TSE escreve 'PC do B' num arquivo e 'PCDOB' no outro. Sem normalizar,
    cada grafia viraria um partido."""
    assert normalizar_sigla("PC do B") == normalizar_sigla("PCDOB") == "PCDOB"
    assert normalizar_sigla("MISSÃO") == normalizar_sigla("missao") == "MISSAO"
    assert normalizar_sigla(None) == ""


# ------------------------------------------------------------------ o indice

def _indice():
    i = IndiceDePartidos()
    i.registrar(14, "PTB", "id-ptb")                    # desde sempre
    i.registrar(14, "MISSÃO", "id-missao", 2025)
    i.registrar(13, "PT", "id-pt")
    return i


def test_a_sigla_do_arquivo_decide_antes_do_ano():
    """A sigla que vem na linha e a melhor evidencia de qual partido era. Vale
    mesmo se o ano apontasse para a outra linha."""
    i = _indice()
    assert i.achar(14, "PTB", 2026) == "id-ptb"
    assert i.achar(14, "MISSAO", 2018) == "id-missao"


def test_sem_sigla_que_case_vale_a_linha_do_ano():
    i = _indice()
    assert i.achar(14, None, 2022) == "id-ptb"
    assert i.achar(14, None, 2026) == "id-missao"
    assert i.achar(14, "SIGLA NOVA", 2022) == "id-ptb"
    # Sem ano (filiacao, que e retrato de hoje): a mais recente.
    assert i.achar(14) == "id-missao"


def test_numero_desconhecido_devolve_vazio_para_quem_chamou_criar():
    i = _indice()
    assert i.achar(99, "XX", 2026) is None
    assert not i.conhece(99)
    assert i.achar_exato(13, "PL") is None


def test_partido_atual_e_o_de_maior_valid_from():
    velho = Party(number=14, abbreviation="PTB", name="PTB")
    novo = Party(number=14, abbreviation="MISSÃO", name="Missao", valid_from=2025)
    assert partido_atual([velho, novo]) is novo
    assert partido_atual([velho]) is velho
    assert partido_atual([]) is None


# ---------------------------------------------------------------- a sucessao

def test_partido_fundido_vai_para_o_numero_do_sucessor():
    assert numero_sucessor(14, 2022) == 25      # PTB -> PRD
    assert numero_sucessor(51, 2022) == 25      # Patriota -> PRD
    assert numero_sucessor(90, 2022) == 77      # PROS -> Solidariedade
    assert numero_sucessor(19, 2022) == 20      # Podemos mudou de numero


def test_numero_reaproveitado_nao_herda_o_sucessor_do_antigo_dono():
    """O 14 de 2026 e o Missao, que nao tem nada a ver com o PRD. Se a regra
    valesse para qualquer ano, o Missao seria somado a bancada do PRD."""
    assert numero_sucessor(14, 2026) == 14


def test_partido_sem_mudanca_fica_como_esta():
    assert numero_sucessor(13, 2022) == 13
    assert numero_sucessor(20, 2022) == 20      # PSC: o numero passou ao Podemos


def test_sucessoes_se_encadeiam_ate_o_partido_de_hoje():
    assert numero_sucessor(44, 2018) == 25      # PRP -> Patriota -> PRD
    assert numero_sucessor(31, 2018) == 20      # PHS -> Podemos (19) -> 20
    assert numero_sucessor(26, 2002) == 25      # PAN -> PTB -> PRD
    assert numero_sucessor(25, 2020) == 44      # DEM -> Uniao


def test_numeros_que_se_revezam_nao_dao_volta_infinita():
    """25 -> 44 -> 51 -> 25 formam um ciclo na tabela. O ano e o que quebra o
    ciclo: o 44 de 2022 e o Uniao, que nao foi a lugar nenhum."""
    assert numero_sucessor(44, 2022) == 44
    assert numero_sucessor(25, 2024) == 25      # ja e o PRD


def test_linhagem_do_prd_junta_ptb_e_patriota_e_deixa_o_dem_de_fora():
    assert trechos_da_linhagem(25) == [
        (25, 2021, None),       # o proprio 25, so depois de deixar de ser DEM
        (14, None, 2024),       # PTB
        (26, None, 2006),       # PAN, via PTB
        (41, None, 2002),       # PSD antigo, via PTB
        (44, None, 2018),       # PRP, via Patriota
        (51, None, 2024),       # Patriota
    ]


def test_partido_extinto_sem_dono_novo_mostra_a_propria_historia():
    """PSL (17), Patriota (51), PROS (90): ninguem reusou o numero. A pagina
    deles tem de mostrar o que existiu, nao ficar vazia."""
    assert trechos_da_linhagem(17) == [(17, None, 2021)]
    assert trechos_da_linhagem(90) == [(90, None, 2024)]
    # O 19 foi do Podemos ate 2022. O PHS, que se incorporou a ele em 2019,
    # segue a corrente ate o numero de HOJE do Podemos (20), nao para no 19.
    assert trechos_da_linhagem(19) == [(19, None, 2024)]
    assert (31, None, 2018) in trechos_da_linhagem(20)


def test_rede_e_novo_nao_herdam_os_partidos_de_2002():
    """Em 2002 o 18 era do PST e o 30 do PGT, incorporados ao PL em 2003."""
    assert trechos_da_linhagem(18) == [(18, 2002, None)]
    assert trechos_da_linhagem(30) == [(30, 2002, None)]
    assert numero_sucessor(18, 2002) == 22
    assert numero_sucessor(30, 2022) == 30
    assert (18, None, 2002) in trechos_da_linhagem(22)


def test_linhagem_do_missao_nao_herda_o_ptb():
    assert trechos_da_linhagem(14) == [(14, 2024, None)]


def test_partido_que_so_mudou_de_nome_tem_uma_faixa_so():
    assert trechos_da_linhagem(35) == [(35, None, None)]


# ------------------------------------------------- o importador do registro

_CAB = ("ANO_ELEICAO;NM_TIPO_ELEICAO;NR_TURNO;CD_ELEICAO;DS_ELEICAO;SG_UF;"
        "CD_CARGO;DS_CARGO;SQ_CANDIDATO;NR_CANDIDATO;NM_CANDIDATO;"
        "NM_URNA_CANDIDATO;DS_SITUACAO_CANDIDATURA;NR_PARTIDO;SG_PARTIDO;"
        "NM_PARTIDO")


def _zip_registro(tmp_path, linhas):
    caminho = tmp_path / "consulta_cand_2026.zip"
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr(
            "consulta_cand_2026_BRASIL.csv",
            (_CAB + "\n" + "\n".join(linhas) + "\n").encode("latin-1"),
        )
    return caminho


_MISSAO = ("2026;ORDINARIA;1;6257;Federal 2026;BR;1;PRESIDENTE;900;14;RENAN;"
           "RENAN;APTO;14;MISSÃO;PARTIDO MISSÃO")
_PCDOB = ("2026;ORDINARIA;1;6259;Estaduais 2026;RJ;3;GOVERNADOR;901;65;ANA;"
          "ANA;APTO;65;PCDOB;PARTIDO COMUNISTA DO BRASIL")


def test_numero_conhecido_com_sigla_nova_abre_epoca_em_vez_de_herdar(
    tmp_path, db_session,
):
    """O teste do defeito real: o 14 ja existia como PTB."""
    ptb = Party(number=14, abbreviation="PTB", name="Partido Trabalhista Brasileiro")
    db_session.add(ptb)
    db_session.commit()

    r = importar_candidatos_do_registro(
        db_session, _zip_registro(tmp_path, [_MISSAO]), ano=2026)

    assert r["partidos_criados"] == 1
    cand = db_session.query(Candidate).filter_by(sq_candidato=900).one()
    partido = db_session.get(Party, cand.party_id)
    assert (partido.abbreviation, partido.valid_from) == ("MISSÃO", 2026)
    assert cand.party_id != ptb.id
    # O PTB continua la, intacto, para as eleicoes em que existiu.
    assert db_session.get(Party, ptb.id).abbreviation == "PTB"


def test_outra_grafia_da_mesma_sigla_nao_abre_epoca(tmp_path, db_session):
    pcdob = Party(number=65, abbreviation="PC do B", name="Partido Comunista do Brasil")
    db_session.add(pcdob)
    db_session.commit()

    r = importar_candidatos_do_registro(
        db_session, _zip_registro(tmp_path, [_PCDOB]), ano=2026)

    assert r["partidos_criados"] == 0
    cand = db_session.query(Candidate).filter_by(sq_candidato=901).one()
    assert cand.party_id == pcdob.id


def test_partido_de_numero_inedito_nasce_sem_data(tmp_path, db_session):
    """Numero que o banco nunca viu nao e 'epoca nova' de nada."""
    importar_candidatos_do_registro(
        db_session, _zip_registro(tmp_path, [_MISSAO]), ano=2026)
    assert db_session.query(Party).filter_by(number=14).one().valid_from is None


# ------------------------------------------------------------------ as rotas

def _dois_no_14(db):
    ptb = Party(number=14, abbreviation="PTB", name="Partido Trabalhista Brasileiro")
    missao = Party(number=14, abbreviation="MISSÃO", name="Partido Missão",
                   valid_from=2025)
    pt = Party(number=13, abbreviation="PT", name="Partido dos Trabalhadores")
    db.add_all([ptb, missao, pt])
    db.flush()
    return ptb, missao


def test_lista_de_partidos_mostra_um_por_numero_com_o_nome_de_hoje(
    client, tenant_a, db_session,
):
    _, _, token = tenant_a
    _dois_no_14(db_session)
    db_session.commit()

    r = client.get("/api/v1/tse/parties", headers=_auth(token))
    assert r.status_code == 200, r.text
    por_numero = [(p["number"], p["abbreviation"]) for p in r.json()]
    assert por_numero == [(13, "PT"), (14, "MISSÃO")]


def test_pagina_do_partido_nao_quebra_com_duas_linhas_no_numero(
    client, tenant_a, db_session,
):
    """Antes havia um scalar_one_or_none() na filiacao: com duas linhas no
    mesmo numero ele levantaria MultipleResultsFound e a rota daria 500."""
    _, _, token = tenant_a
    ptb, missao = _dois_no_14(db_session)
    e22 = Election(tse_code=546, year=2022, round=1, name="Geral 2022")
    e26 = Election(tse_code=6259, year=2026, round=1, name="Geral 2026")
    db_session.add_all([e22, e26])
    db_session.flush()
    for sq, eleicao, partido in ((1, e22, ptb), (2, e26, missao)):
        db_session.add(Candidate(
            election_id=eleicao.id, party_id=partido.id, sq_candidato=sq,
            number=14, name=f"C{sq}", urn_name=f"C{sq}", office_code=6,
            office_name="DEPUTADO FEDERAL", state="RJ", total_votes=100,
        ))
    db_session.commit()

    filiacao = client.get("/api/v1/tse/parties/14/membership", headers=_auth(token))
    assert filiacao.status_code == 200, filiacao.text
    assert filiacao.json()["party"]["acronym"] == "MISSÃO"

    evolucao = client.get("/api/v1/tse/parties/14/evolution", headers=_auth(token))
    assert evolucao.status_code == 200, evolucao.text
    assert evolucao.json()["party"]["abbreviation"] == "MISSÃO"
    # So 2026: o candidato de 2022 era do PTB, que e outro partido.
    assert [i["year"] for i in evolucao.json()["items"]] == [2026]


def test_historia_do_ptb_aparece_no_prd_que_o_sucedeu(client, tenant_a, db_session):
    _, _, token = tenant_a
    ptb, _missao = _dois_no_14(db_session)
    prd = Party(number=25, abbreviation="PRD", name="Partido Renovação Democrática")
    e20 = Election(tse_code=426, year=2020, round=1, name="Municipal 2020")
    e22 = Election(tse_code=546, year=2022, round=1, name="Geral 2022")
    e24 = Election(tse_code=619, year=2024, round=1, name="Municipal 2024")
    db_session.add_all([prd, e20, e22, e24])
    db_session.flush()
    # 2020: o 25 ainda era DEM. 2022: PTB. 2024: PRD ja com o proprio numero.
    for sq, eleicao, partido in ((1, e20, prd), (2, e22, ptb), (3, e24, prd)):
        db_session.add(Candidate(
            election_id=eleicao.id, party_id=partido.id, sq_candidato=sq,
            number=partido.number, name=f"C{sq}", urn_name=f"C{sq}",
            office_code=13, office_name="VEREADOR", state="RJ", total_votes=10,
        ))
    db_session.commit()

    r = client.get("/api/v1/tse/parties/25/evolution", headers=_auth(token))
    assert r.status_code == 200, r.text
    # 2020 fica de fora (era o DEM, hoje no Uniao); 2022 entra pelo PTB.
    assert [i["year"] for i in r.json()["items"]] == [2022, 2024]


def test_busca_e_ranking_por_partido_seguem_a_linhagem(client, tenant_a, db_session):
    """Regressao: so a evolucao seguia a linhagem. A busca de candidatos e o
    ranking filtravam pelo NUMERO, entao a pagina do Missao listava os
    candidatos do PTB sob o nome Missao."""
    _, _, token = tenant_a
    ptb, missao = _dois_no_14(db_session)
    prd = Party(number=25, abbreviation="PRD", name="Partido Renovação Democrática")
    e22 = Election(tse_code=546, year=2022, round=1, name="Geral 2022")
    e26 = Election(tse_code=6259, year=2026, round=1, name="Geral 2026")
    db_session.add_all([prd, e22, e26])
    db_session.flush()
    for sq, eleicao, partido, nome in (
        (1, e22, ptb, "DO PTB"), (2, e26, missao, "DO MISSAO"), (3, e26, prd, "DO PRD"),
    ):
        db_session.add(Candidate(
            election_id=eleicao.id, party_id=partido.id, sq_candidato=sq,
            number=partido.number, name=nome, urn_name=nome, office_code=6,
            office_name="DEPUTADO FEDERAL", state="RJ", total_votes=100 + sq,
        ))
    db_session.commit()

    def nomes(caminho):
        r = client.get("/api/v1/tse" + caminho, headers=_auth(token))
        assert r.status_code == 200, r.text
        itens = r.json()["items"]
        return sorted((i.get("candidate") or i)["urn_name"] for i in itens)

    # O 14 de hoje e o Missao: o candidato do PTB nao entra.
    assert nomes("/candidates?party_number=14") == ["DO MISSAO"]
    # O PTB virou PRD: o candidato dele aparece na pagina do PRD.
    assert nomes("/candidates?party_number=25") == ["DO PRD", "DO PTB"]
    assert nomes("/stats/top-candidates?year=2022&office_code=6&party_number=25") == ["DO PTB"]
    assert nomes("/stats/top-candidates?year=2022&office_code=6&party_number=14") == []

    # E o desempenho diz a que partido de hoje cada linha pertence.
    perf = client.get(
        "/api/v1/tse/stats/party-performance?year=2022&office_code=6",
        headers=_auth(token),
    ).json()["items"]
    assert [(i["party"]["abbreviation"], i["lineage_number"]) for i in perf] == [("PTB", 25)]


def test_partido_renomeado_mantem_a_historia_inteira(client, tenant_a, db_session):
    """35: PMB virou DEMOCRATA. E o mesmo partido — a serie junta as duas linhas."""
    _, _, token = tenant_a
    pmb = Party(number=35, abbreviation="PMB", name="Partido da Mulher Brasileira")
    dem = Party(number=35, abbreviation="DEMOCRATA", name="Democrata", valid_from=2025)
    e24 = Election(tse_code=619, year=2024, round=1, name="Municipal 2024")
    e26 = Election(tse_code=6259, year=2026, round=1, name="Geral 2026")
    db_session.add_all([pmb, dem, e24, e26])
    db_session.flush()
    for sq, eleicao, partido in ((1, e24, pmb), (2, e26, dem)):
        db_session.add(Candidate(
            election_id=eleicao.id, party_id=partido.id, sq_candidato=sq,
            number=35, name=f"C{sq}", urn_name=f"C{sq}", office_code=13,
            office_name="X", state="RJ", total_votes=10,
        ))
    db_session.commit()

    r = client.get("/api/v1/tse/parties/35/evolution", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["party"]["abbreviation"] == "DEMOCRATA"
    assert [i["year"] for i in r.json()["items"]] == [2024, 2026]


# ------------------------------------------------------- sigla de cada epoca

def test_sigla_no_ano_devolve_o_nome_que_o_numero_tinha():
    from app.utils.partidos import sigla_no_ano

    # 25: PFL, depois DEM, hoje PRD.
    assert [sigla_no_ano(25, a, "PRD") for a in (2002, 2006, 2010, 2018, 2020, 2024, 2026)] == [
        "PFL", "PFL", "DEM", "DEM", "DEM", "PRD", "PRD",
    ]
    # 22: PL, virou PR e voltou a ser PL — a epoca do meio nao pode sumir.
    assert [sigla_no_ano(22, a, "PL") for a in (2006, 2010, 2018, 2022)] == [
        "PL", "PR", "PR", "PL",
    ]
    # 44 era PRP ate 2018; o Uniao so existe depois.
    assert (sigla_no_ano(44, 2018, "UNIÃO"), sigla_no_ano(44, 2022, "UNIÃO")) == ("PRP", "UNIÃO")
    # Numero sem troca de nome: vale o que esta no banco.
    assert sigla_no_ano(13, 2002, "PT") == "PT"
    # 14 e 35 ja tem linha por epoca no banco: a tabela nao mexe.
    assert sigla_no_ano(14, 2018, "PTB") == "PTB"
