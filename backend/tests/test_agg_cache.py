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
