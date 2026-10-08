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

Limite de memória: as chaves são por-entidade e de alta cardinalidade
(muni_top:{muni}:{cargo}:{ano}:{limit}, candidate zone/timeline por id...), e
navegar muitos municípios/candidatos poderia acumular MILHARES de respostas
grandes (winners-map/top-candidates têm centenas de KB) vivas por todo o tempo
de vida do processo — risco de OOM no box de 768MB. Por isso é um LRU com teto:
insere no fim, despeja o mais antigo quando estoura MAX_ENTRIES, e remove de
fato as entradas expiradas ao tocá-las (antes só eram ignoradas, nunca liberadas).
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Callable, TypeVar

T = TypeVar("T")

# TTL padrão (segundos). Sync limpa o cache, então pode ser generoso.
# Dados TSE históricos não mudam — 4h é confortável. Warmup periódico
# re-aquece antes do TTL expirar, mantendo o cache sempre "quente".
DEFAULT_TTL = 14400  # 4h

# Teto de entradas. Cada valor pode ter centenas de KB; algumas centenas de
# entradas cabem folgado no limite de 768MB da API sem risco de OOM.
MAX_ENTRIES = 256

# OrderedDict = ordem de uso (LRU): fim = mais recente, início = mais antigo.
_store: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()
_lock = threading.Lock()


def _get_fresh_locked(key: str, ttl: int, now: float) -> Any | None:
    """Sob lock: retorna valor fresco (marcando como recém-usado) ou None.
    Se expirado, remove a entrada (libera memória em vez de deixá-la pra sempre)."""
    hit = _store.get(key)
    if hit is None:
        return None
    if (now - hit[0]) >= ttl:
        # Expirado: remove de fato (antes ficava até um clear_agg_cache()).
        del _store[key]
        return None
    _store.move_to_end(key)  # LRU: acesso conta como "recente"
    return hit[1]


def _set_locked(key: str, value: Any, now: float) -> None:
    """Sob lock: grava/atualiza e despeja o mais antigo se estourar o teto."""
    _store[key] = (now, value)
    _store.move_to_end(key)
    while len(_store) > MAX_ENTRIES:
        _store.popitem(last=False)  # remove o menos recentemente usado


def cached_agg(key: str, compute: Callable[[], T], ttl: int = DEFAULT_TTL) -> T:
    """Retorna o valor cacheado se fresco; senão computa, guarda e retorna."""
    now = time.monotonic()
    with _lock:
        cached = _get_fresh_locked(key, ttl, now)
        if cached is not None:
            return cached
    # Computa fora do lock (queries longas não bloqueiam outras chaves)
    value = compute()
    with _lock:
        _set_locked(key, value, time.monotonic())
    return value


def agg_get(key: str, ttl: int = DEFAULT_TTL) -> Any | None:
    """Retorna o valor cacheado fresco, ou None se ausente/expirado.
    Os endpoints sempre retornam objetos (nunca None), então None = miss."""
    now = time.monotonic()
    with _lock:
        return _get_fresh_locked(key, ttl, now)


def agg_set(key: str, value: Any) -> None:
    with _lock:
        _set_locked(key, value, time.monotonic())


def clear_agg_cache() -> None:
    """Esvazia tudo — chamado após disparar uma sincronização do TSE."""
    with _lock:
        _store.clear()


def _ano(token: str) -> int | None:
    return int(token) if len(token) == 4 and token.isdigit() and 1990 <= int(token) <= 2100 else None


def _so_historico(key: str, ano_vivo: int) -> bool:
    """A chave fala SÓ de eleição fechada? (então o valor dela não muda)

    As chaves são "prefixo:campo:campo:...", com o ano num dos campos. Na dúvida
    a resposta é não — errar para o lado de limpar custa uma consulta refeita;
    errar para o lado de manter mostraria número velho da apuração.
    """
    partes = key.split(":")
    if partes[0] == "census":
        # Dado do IBGE: a apuração não muda bairro nem setor. Sem esta linha o
        # índice da busca de bairros (10+ s para montar) era jogado fora a cada
        # passada da captura, e a busca seguinte de cada usuário o refazia.
        return True
    if partes[0] == "cand":
        # Busca de candidato: o texto digitado é um campo livre (pode ser
        # "2022") e sem filtro de ano a busca atravessa todas as eleições. Só
        # o campo do ano decide — o 7º a contar do fim.
        ano = _ano(partes[-7]) if len(partes) >= 8 else None
        return ano is not None and ano != ano_vivo
    anos = {a for a in map(_ano, partes[1:]) if a is not None}
    return bool(anos) and ano_vivo not in anos


def limpar_cache_da_apuracao(ano_vivo: int) -> tuple[int, int]:
    """Tira do cache o que a apuração pode ter mudado; devolve (removidas, mantidas).

    A captura ao vivo avisa a API a cada 2 minutos. Esvaziar TUDO, como se fazia,
    jogava fora junto as agregações pesadas das eleições antigas (desempenho de
    partido de 2022 = dezenas de segundos neste servidor), que nunca mais
    ficavam quentes: a tela de qualquer ano fechado recalculava do zero a cada
    visita, durante os dias inteiros da apuração.
    """
    with _lock:
        descartar = [k for k in _store if not _so_historico(k, ano_vivo)]
        for k in descartar:
            del _store[k]
        return len(descartar), len(_store)
