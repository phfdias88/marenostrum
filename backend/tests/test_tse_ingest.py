"""
Guarda-corpos da ingestao do TSE para a apuracao de outubro/2026.

O que estes testes protegem nao e "a importacao funciona" — e que ela FALHE
ALTO quando o dado nao vier como esperado. Este projeto ja gravou milhares de
linhas todas nulas porque o IBGE mudou a caixa de uma variavel, e o log dizia
que tinha dado certo.
"""
import io
import zipfile

import pytest

from app.models.tse import Candidate, Election, Municipality, Party, VoteResult
from app.services.tse_ingest import (
    EstruturaInesperadaError,
    arquivos_prontos,
    cobertura,
    ler_cabecalho,
    validar_estrutura,
)


def _zip_com_colunas(tmp_path, nome, colunas, linha=None):
    caminho = tmp_path / nome
    buf = io.StringIO()
    buf.write(";".join(colunas) + "\n")
    if linha:
        buf.write(";".join(linha) + "\n")
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("dados.csv", buf.getvalue().encode("latin-1"))
    return caminho


# ------------------------------------------------------------- validacao

def test_arquivo_completo_passa(tmp_path):
    z = _zip_com_colunas(tmp_path, "ok.zip", [
        "SQ_CANDIDATO", "CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO",
        "QT_VOTOS", "NR_TURNO",
    ])
    r = validar_estrutura(z, "votacao_secao")
    assert r["validado"] is True
    assert r["colunas"] == 6


def test_coluna_que_sumiu_derruba_o_job_dizendo_qual(tmp_path):
    """O caso que importa: o TSE muda o layout e a importacao TEM de morrer
    antes de escrever, nomeando a coluna — nao gravar nulo em silencio."""
    z = _zip_com_colunas(tmp_path, "faltando.zip", [
        "SQ_CANDIDATO", "CD_MUNICIPIO", "QT_VOTOS", "NR_TURNO",
    ])
    with pytest.raises(EstruturaInesperadaError) as erro:
        validar_estrutura(z, "votacao_secao")

    msg = str(erro.value)
    assert "NR_ZONA" in msg and "NR_LOCAL_VOTACAO" in msg
    assert "Nada foi importado" in msg


def test_coluna_NOVA_nao_derruba_nada(tmp_path):
    """O TSE acrescenta campo com frequencia e isso nunca quebrou nada —
    recusar por coluna a mais criaria falha onde nao ha problema."""
    z = _zip_com_colunas(tmp_path, "extra.zip", [
        "SQ_CANDIDATO", "CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO",
        "QT_VOTOS", "NR_TURNO", "CAMPO_NOVO_DO_TSE",
    ])
    r = validar_estrutura(z, "votacao_secao")
    assert r["validado"] is True
    assert "CAMPO_NOVO_DO_TSE" in r["colunas_novas"]


def test_bom_de_bom_no_cabecalho_nao_esconde_a_primeira_coluna(tmp_path):
    """Arquivo do TSE as vezes vem com BOM. Sem tratar, a 1a coluna vira
    '\\ufeffSQ_CANDIDATO' e o job acusaria falta de uma coluna que existe."""
    caminho = tmp_path / "bom.zip"
    texto = "﻿" + ";".join([
        "SQ_CANDIDATO", "CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO",
        "QT_VOTOS", "NR_TURNO",
    ]) + "\n"
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("dados.csv", texto.encode("utf-8"))
    assert "SQ_CANDIDATO" in ler_cabecalho(caminho)


def test_processador_sem_regra_nao_inventa_validacao(tmp_path):
    z = _zip_com_colunas(tmp_path, "x.zip", ["QUALQUER"])
    r = validar_estrutura(z, "processador_que_nao_existe")
    assert r["validado"] is False


# -------------------------------------------------------------- cobertura

def _seed_parcial(db):
    """Uma UF ficticia (XX, nao ZZ: ZZ e o exterior de verdade) com 3 municipios, mas voto so em 1 — a capital saiu, a cidade
    pequena nao. E exatamente o cenario que o socio descreveu."""
    e = Election(tse_code=900, year=2026, round=1, name="Geral 2026")
    p = Party(number=10, abbreviation="ZZZ", name="Partido ZZZ")
    db.add_all([e, p])
    db.flush()

    munis = [
        Municipality(tse_code=90001 + i, name=f"Cidade {i}", state="XX")
        for i in range(3)
    ]
    db.add_all(munis)
    db.flush()

    c = Candidate(
        election_id=e.id, party_id=p.id, sq_candidato=900001, number=10,
        name="X", urn_name="X", office_code=11, office_name="PREFEITO",
        state="XX", total_votes=10,
    )
    db.add(c)
    db.flush()
    db.add(VoteResult(candidate_id=c.id, municipality_id=munis[0].id, votes=10))
    db.commit()
    return munis


def test_cobertura_mostra_o_que_falta(db_session):
    _seed_parcial(db_session)
    r = cobertura(db_session, ano=2026)

    zz = next(l for l in r["por_uf"] if l["uf"] == "XX")
    assert zz["municipios_com_dado"] == 1
    assert zz["municipios_esperados"] == 3
    assert zz["faltam"] == 2
    assert r["situacao"] == "vazio"     # nenhuma UF fechou


def test_exterior_nao_entra_na_conta(db_session):
    """ZZ e o codigo do TSE pro exterior: 189 cidades onde brasileiro vota fora
    do pais, e la so ha cargo federal. Conta-las como "faltando" numa apuracao
    municipal inflaria o numero justamente na noite em que ele precisa ser
    confiavel."""
    _seed_parcial(db_session)
    db_session.add(Municipality(tse_code=99001, name="Lisboa", state="ZZ"))
    db_session.commit()

    r = cobertura(db_session, ano=2026)
    assert all(l["uf"] != "ZZ" for l in r["por_uf"])
    assert r["exterior"]["cidades"] == 1


def test_cobertura_de_ano_sem_dado_nao_quebra(db_session):
    _seed_parcial(db_session)
    r = cobertura(db_session, ano=1998)
    zz = next(l for l in r["por_uf"] if l["uf"] == "XX")
    assert zz["municipios_com_dado"] == 0
    assert r["situacao"] == "vazio"


# ------------------------------------------------- porta de entrada manual

def test_lista_arquivos_e_acusa_download_interrompido(tmp_path):
    bom = _zip_com_colunas(tmp_path, "candidato_munzona_2026.zip", ["A"])
    (tmp_path / "pela_metade.zip").write_bytes(b"PK\x03\x04 truncado")

    itens = {i["arquivo"]: i for i in arquivos_prontos(tmp_path)}
    assert itens["candidato_munzona_2026.zip"]["valido"] is True
    assert itens["candidato_munzona_2026.zip"]["dataset"] == "candidato_munzona_2026"
    # Download interrompido tem de aparecer como invalido ANTES da ingestao.
    assert itens["pela_metade.zip"]["valido"] is False
    assert bom.exists()


def test_diretorio_inexistente_devolve_lista_vazia(tmp_path):
    assert arquivos_prontos(tmp_path / "nao_existe") == []
