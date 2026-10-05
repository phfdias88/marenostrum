"""
Cache de dataset VIVO — o arquivo que muda durante a apuracao.

O cache normal reusa o zip se ele ja existe em disco. Para historico esta certo:
o TSE nao muda eleicao passada. Na noite da apuracao esta errado: o arquivo de
resultado nasce so com o cabecalho (350 KB, zero linhas) e vai crescendo. Quem
baixasse a casca cedo ficaria preso nela, importando "com sucesso" um arquivo
vazio a noite inteira.
"""
import httpx

from app.utils import tse_sync
from app.utils.tse_sync import DATASETS, _cache_ainda_vale


class _Resp:
    def __init__(self, status=200, tamanho=None):
        self.status_code = status
        self.headers = {} if tamanho is None else {"content-length": str(tamanho)}


def _arquivo(tmp_path, bytes_):
    p = tmp_path / "resultado.zip"
    p.write_bytes(b"x" * bytes_)
    return p


def test_arquivo_cresceu_no_tse_invalida_o_cache(tmp_path, monkeypatch):
    """O caso da noite: em disco a casca de 350 KB, no TSE ja o resultado."""
    local = _arquivo(tmp_path, 350)
    monkeypatch.setattr(httpx, "head", lambda *a, **k: _Resp(tamanho=48_000))
    assert _cache_ainda_vale("http://tse/x.zip", local) is False


def test_mesmo_tamanho_reusa_o_disco(tmp_path, monkeypatch):
    local = _arquivo(tmp_path, 1234)
    monkeypatch.setattr(httpx, "head", lambda *a, **k: _Resp(tamanho=1234))
    assert _cache_ainda_vale("http://tse/x.zip", local) is True


def test_tse_bloqueando_nao_apaga_o_que_temos(tmp_path, monkeypatch):
    """O TSE ja ficou semanas devolvendo 403 a cliente automatizado. O arquivo
    em disco pode ter sido entregue a mao justamente por isso — apaga-lo
    deixaria o job sem nada."""
    local = _arquivo(tmp_path, 500)
    monkeypatch.setattr(httpx, "head", lambda *a, **k: _Resp(status=403))
    assert _cache_ainda_vale("http://tse/x.zip", local) is True


def test_rede_caindo_nao_apaga_o_que_temos(tmp_path, monkeypatch):
    local = _arquivo(tmp_path, 500)

    def _explode(*a, **k):
        raise httpx.ConnectError("sem rede")

    monkeypatch.setattr(httpx, "head", _explode)
    assert _cache_ainda_vale("http://tse/x.zip", local) is True


def test_tse_sem_informar_tamanho_confia_no_disco(tmp_path, monkeypatch):
    local = _arquivo(tmp_path, 500)
    monkeypatch.setattr(httpx, "head", lambda *a, **k: _Resp(tamanho=None))
    assert _cache_ainda_vale("http://tse/x.zip", local) is True


def test_2026_esta_cadastrado_e_marcado_como_vivo():
    """Sem estas entradas o job de sync nem aceita o dataset de 2026."""
    for nome in ("candidato_munzona_2026", "locais_votacao_2026",
                 "consulta_cand_2026", "zona_votos_2026",
                 "votacao_secao_2026_RJ", "votacao_secao_2026_SP"):
        assert nome in DATASETS, nome
        assert DATASETS[nome]["year"] == 2026
        assert DATASETS[nome].get("vivo") is True, f"{nome} tem de ser vivo"


def test_historico_nao_e_vivo():
    """Dataset de eleicao passada nao muda: conferir o tamanho a cada job seria
    uma requisicao a toa e arriscaria rebaixar 500 MB sem necessidade."""
    assert not DATASETS["candidato_munzona_2022"].get("vivo")
    assert not DATASETS["votacao_secao_2024_RJ"].get("vivo")


def test_as_27_ufs_tem_secao_de_2026():
    faltando = [uf for uf in tse_sync.ALL_UFS
                if f"votacao_secao_2026_{uf}" not in DATASETS]
    assert faltando == []


# ------------------------------------------------ nacional + estaduais no zip
# Em 2026 o TSE mudou a EMBALAGEM: o zip de locais passou a trazer um CSV por
# UF mais um _BRASIL que e a concatenacao de todos. As colunas sao identicas,
# entao a validacao de estrutura passa — e cada linha conta duas vezes. A
# primeira carga de locais de 2026 gravou 317 milhoes de eleitores num pais que
# tem 158.

from app.utils.tse_sync import _sem_duplicata_nacional, iter_csv_rows


def test_nacional_junto_dos_estaduais_le_so_o_nacional():
    nomes = ["x_2026_RJ.csv", "x_2026_SP.csv", "x_2026_BRASIL.csv"]
    assert _sem_duplicata_nacional(nomes) == ["x_2026_BRASIL.csv"]


def test_so_estaduais_le_todos():
    nomes = ["x_2026_RJ.csv", "x_2026_SP.csv"]
    assert _sem_duplicata_nacional(nomes) == nomes


def test_arquivo_unico_como_em_2024_segue_lido():
    assert _sem_duplicata_nacional(["x_2024.csv"]) == ["x_2024.csv"]


def test_so_o_nacional_segue_lido():
    assert _sem_duplicata_nacional(["x_2026_BRASIL.csv"]) == ["x_2026_BRASIL.csv"]


def test_leitura_do_zip_nao_conta_em_dobro(tmp_path):
    """Ponta a ponta: zip com 2 estaduais + nacional tem de render 2 linhas,
    nao 4."""
    import zipfile

    caminho = tmp_path / "locais_2026.zip"
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("l_2026_RJ.csv", "UF;V\nRJ;10\n")
        z.writestr("l_2026_SP.csv", "UF;V\nSP;20\n")
        z.writestr("l_2026_BRASIL.csv", "UF;V\nRJ;10\nSP;20\n")

    linhas = [row for _, row in iter_csv_rows(caminho)]
    assert len(linhas) == 2
    assert sum(int(r["V"]) for r in linhas) == 30     # e nao 60
