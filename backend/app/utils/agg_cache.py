"""
Cache TTL em memória para agregações pesadas do TSE.

Por quê: party-performance, winners-map e contagens varrem milhões de linhas
(party-performance ~3s sobre 8,7M votos). Os dados do TSE são ESTÁTICOS entre
sincronizações, então cachear o resultado por alguns minutos torna as
navegações repetidas instantâneas. A API roda com 1 worker uvicorn, então o
cache em processo tem ~100% de acerto entre requisições.

Uso:
    from app.utils.agg_cache import cached_agg, clear_agg_cache
    key = f"party_perf:{year}:{office}:{state}"
    return cached_agg(key, lambda: _compute(...))

Invalidação: clear_agg_cache() é chamada quando uma sync TSE é disparada.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")

# TTL padrão (segundos). Sync limpa o cache, então pode ser generoso.
# Dados TSE históricos não mudam — 4h é confortável. Warmup periódico
# re-aquece antes do TTL expirar, mantendo o cache sempre "quente".
DEFAULT_TTL = 14400  # 4h

_store: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()


def cached_agg(key: str, compute: Callable[[], T], ttl: int = DEFAULT_TTL) -> T:
    """Retorna o valor cacheado se fresco; senão computa, guarda e retorna."""
    now = time.monotonic()
    with _lock:
        hit = _store.get(key)
        if hit is not None and (now - hit[0]) < ttl:
            return hit[1]
    # Computa fora do lock (queries longas não bloqueiam outras chaves)
    value = compute()
    with _lock:
        _store[key] = (time.monotonic(), value)
    return value


def agg_get(key: str, ttl: int = DEFAULT_TTL) -> Any | None:
    """Retorna o valor cacheado fresco, ou None se ausente/expirado.
    Os endpoints sempre retornam objetos (nunca None), então None = miss."""
    now = time.monotonic()
    with _lock:
        hit = _store.get(key)
        if hit is not None and (now - hit[0]) < ttl:
            return hit[1]
    return None


def agg_set(key: str, value: Any) -> None:
    with _lock:
        _store[key] = (time.monotonic(), value)


def clear_agg_cache() -> None:
    """Esvazia tudo — chamado após disparar uma sincronização do TSE."""
    with _lock:
        _store.clear()
