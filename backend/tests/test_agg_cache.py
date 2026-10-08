"""
Testes do cache de agregações (LRU com TTL). Puro Python, sem DB.
Cobre o fix de performance/memória: teto de entradas + evicção LRU + expiração
que de fato libera a entrada.
"""
from __future__ import annotations

import app.utils.agg_cache as ac
from app.utils.agg_cache import agg_get, agg_set, cached_agg, clear_agg_cache


def setup_function(_):
    clear_agg_cache()


def test_set_get_roundtrip():
    agg_set("k", {"v": 1})
    assert agg_get("k") == {"v": 1}


def test_miss_returns_none():
    assert agg_get("inexistente") is None


def test_cached_agg_computa_uma_vez():
    calls = []

    def compute():
        calls.append(1)
        return "x"

    assert cached_agg("k", compute) == "x"
    assert cached_agg("k", compute) == "x"
    assert len(calls) == 1  # segundo acesso é hit, não recomputa


def test_expirado_e_removido_do_store():
    agg_set("k", 1)
    # ttl=0 => qualquer idade >= 0 conta como expirado
    assert agg_get("k", ttl=0) is None
    # e a entrada foi liberada (antes ficava presa até clear_agg_cache)
    assert "k" not in ac._store


def test_lru_despeja_o_mais_antigo(monkeypatch):
    monkeypatch.setattr(ac, "MAX_ENTRIES", 3)
    for i in range(5):
        agg_set(f"k{i}", i)
    assert len(ac._store) == 3
    assert agg_get("k0") is None
    assert agg_get("k1") is None
    assert agg_get("k4") == 4


def test_acesso_marca_como_recente(monkeypatch):
    monkeypatch.setattr(ac, "MAX_ENTRIES", 3)
    agg_set("a", 1)
    agg_set("b", 2)
    agg_set("c", 3)
    agg_get("a")        # 'a' passa a ser o mais recentemente usado
    agg_set("d", 4)     # estoura o teto -> despeja o mais antigo, que agora é 'b'
    assert agg_get("b") is None
    assert agg_get("a") == 1
    assert agg_get("c") == 3
    assert agg_get("d") == 4


# ------------------------------------------- limpeza seletiva na apuracao

def _chaves():
    from app.utils import agg_cache
    return set(agg_cache._store)


def test_apuracao_limpa_o_ano_vivo_e_mantem_as_eleicoes_fechadas():
    """Esvaziar tudo a cada 2 minutos deixava o desempenho de partido de 2022
    (dezenas de segundos) recalculando a cada visita, dias a fio."""
    from app.utils.agg_cache import limpar_cache_da_apuracao

    clear_agg_cache()
    vivas = [
        "party_perf:2026:3:", "winners_map:2026:1", "bancada:2026:5",
        "virada:1:2022:2026",              # compara com o ano vivo
        "elec_res:national:None:None:1:2026:500",
    ]
    fechadas = [
        "party_perf:2022:6:", "winners_map:2024:11", "counts:2022",
        "elec_res:state:None:SP:6:2022:500",
        "muni_top:217293ad-fb3f-4002-8d04-72eefa8446f2:11:2024:20",
    ]
    for k in vivas + fechadas:
        agg_set(k, {"x": 1})

    removidas, mantidas = limpar_cache_da_apuracao(2026)

    assert (removidas, mantidas) == (len(vivas), len(fechadas))
    assert _chaves() == set(fechadas)


def test_chave_sem_ano_e_sempre_limpa():
    """Sem ano na chave nao da para saber se ela inclui a apuracao: contagem
    geral, evolucao do partido, comparecimento, linha do tempo do municipio."""
    from app.utils.agg_cache import limpar_cache_da_apuracao

    clear_agg_cache()
    for k in ("counts:None", "party_evo:22", "comparecimento:1:BR:1",
              "muni_timeline:217293ad-fb3f-4002-8d04-72eefa8446f2"):
        agg_set(k, {"x": 1})
    limpar_cache_da_apuracao(2026)
    assert _chaves() == set()


def test_dado_do_censo_sobrevive_a_limpeza_da_apuracao():
    """A apuracao nao muda bairro nem setor, e o indice da busca de bairros
    custa 10+ segundos para montar: jogar fora a cada passada da captura fazia
    a busca seguinte de cada usuario refazer tudo."""
    from app.utils.agg_cache import limpar_cache_da_apuracao

    clear_agg_cache()
    agg_set("census:area_index", [{"nome": "Centro"}])
    agg_set("counts:None", {"x": 1})
    limpar_cache_da_apuracao(2026)
    assert _chaves() == {"census:area_index"}


def test_busca_de_candidato_decide_pelo_campo_do_ano_e_nao_pelo_texto():
    """Quem digita "2022" na busca sem filtro de ano recebe candidatos de todas
    as eleicoes, inclusive a que esta apurando. O texto nao pode valer de ano."""
    from app.utils.agg_cache import limpar_cache_da_apuracao

    clear_agg_cache()
    sem_ano = "cand:2022:None:None:None:None:None:False:None:None:True:50:0"
    de_2022 = "cand:silva:SP:6:None:None:2022:False:None:votes:False:50:0"
    de_2026 = "cand:silva:SP:6:None:None:2026:False:None:votes:False:50:0"
    for k in (sem_ano, de_2022, de_2026):
        agg_set(k, {"x": 1})
    limpar_cache_da_apuracao(2026)
    assert _chaves() == {de_2022}
