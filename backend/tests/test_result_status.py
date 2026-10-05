"""
Como o sistema decide "esta pessoa foi eleita".

O teste tem de ser por PREFIXO. "ELEITO" esta DENTRO de "NAO ELEITO", entao
qualquer checagem por conter traz o derrotado junto — foi assim que o dossie
PDF pintava de verde quem perdeu a eleicao.
"""
from app.utils.tse_pdf import _result_color, GREEN, RED, AMBER, MUTED


def test_nao_eleito_nao_pode_sair_verde_no_dossie():
    """O defeito que estava no ar: o ramo verde vinha antes e casava por
    substring, entao o vermelho nunca era alcancado."""
    assert _result_color("NÃO ELEITO") is RED
    assert _result_color("NAO ELEITO") is RED


def test_as_formas_de_eleito_saem_verdes():
    for status in ("ELEITO", "ELEITO POR QP", "ELEITO POR MÉDIA", "eleito"):
        assert _result_color(status) is GREEN, status


def test_media_sozinho_e_eleito():
    """Ate 2010 o TSE escrevia so 'MEDIA' — 622 candidaturas, todas de cargo
    proporcional, com media de dezenas de milhares de votos."""
    assert _result_color("MÉDIA") is GREEN


def test_suplente_e_ambar_e_desconhecido_e_neutro():
    assert _result_color("SUPLENTE") is AMBER
    assert _result_color("2º TURNO") is MUTED
    assert _result_color(None) is MUTED
    assert _result_color("") is MUTED
