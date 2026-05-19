"""
Foto de candidatos TSE — extracao on-demand via HTTP Range + cache em disco.

Estrategia:
- TSE publica fotos em ZIPs por UF de ~2GB cada (zip total > 30GB).
  Nao cabe na VPS, e mesmo se coubesse, seria caro baixar tudo upfront.
- Usamos `remotezip` (que faz HTTP Range nos bytes do central directory + slot
  do arquivo desejado). So baixamos ~50KB por foto.
- Cache em /var/marenostrum/tse_photos/{UF}/{sq_candidato}.jpg pra evitar
  segunda chamada ao TSE.
- Central directory dos zips estaduais e cacheado em memoria (RemoteZip
  instance) por TTL — evita re-baixar listing de 73k entradas cada hit.

Convencao do nome interno do ZIP:
  F{UF}{SQ_CANDIDATO}_div.jpg   (ex: FMG130001883579_div.jpg)
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Optional

import structlog
from remotezip import RemoteZip

log = structlog.get_logger("marenostrum.tse_photos")

# --------------------------------------------------------- constantes

CDN_BASE = (
    "https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2024/fotos"
)

CACHE_DIR = Path("/var/marenostrum/tse_photos")

# TTL do RemoteZip handle (central directory cacheado).
# Apos isso, recriamos pra liberar memoria e pegar updates do CDN.
_HANDLE_TTL_S = 3600  # 1h

# UFs validas (defensivo — evita SSRF caso state malformado chegue)
VALID_UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
    "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
    "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}

# --------------------------------------------------------- handle cache

# RemoteZip herda de zipfile.ZipFile, que NAO e thread-safe (mantem posicao
# interna do file pointer). Sob carga concorrente, duas threads lendo do mesmo
# handle causa urllib3.ProtocolError "IncompleteRead". Por isso:
# - Um lock POR UF (permite paralelismo entre estados diferentes).
# - Lock cobre TODA a operacao de read, nao so o lookup do handle.
# - Em caso de erro de rede, reseta o handle e tenta de novo.
_handles: dict[str, tuple[RemoteZip, float]] = {}
_handle_locks: dict[str, threading.Lock] = {}
_dict_lock = threading.Lock()  # protege _handles e _handle_locks


def _zip_url(uf: str) -> str:
    return f"{CDN_BASE}/foto_cand2024_{uf}_div.zip"


def _get_lock(uf: str) -> threading.Lock:
    with _dict_lock:
        lock = _handle_locks.get(uf)
        if lock is None:
            lock = threading.Lock()
            _handle_locks[uf] = lock
        return lock


def _get_handle(uf: str, *, force_new: bool = False) -> RemoteZip:
    """
    Devolve RemoteZip pro UF (recria se expirado ou se force_new=True).
    DEVE ser chamado com o lock do UF ja adquirido.
    """
    now = time.monotonic()
    with _dict_lock:
        cached = _handles.get(uf)
        if cached is not None and not force_new:
            handle, created = cached
            if now - created < _HANDLE_TTL_S:
                return handle
        # expirou ou force_new — fecha e recria
        if cached is not None:
            try:
                cached[0].close()
            except Exception:
                pass
            _handles.pop(uf, None)

    log.info(
        "tse_photos_open_zip",
        uf=uf,
        url=_zip_url(uf),
        force_new=force_new,
    )
    handle = RemoteZip(_zip_url(uf))
    with _dict_lock:
        _handles[uf] = (handle, now)
    return handle


# --------------------------------------------------------- API publica


class PhotoNotFound(Exception):
    """Candidato nao tem foto registrada no TSE pra esse UF."""


def get_candidate_photo(uf: str, sq_candidato: int) -> bytes:
    """
    Retorna bytes JPEG da foto do candidato. Levanta PhotoNotFound se nao existir.

    Cache em disco: se /var/marenostrum/tse_photos/{UF}/{SQ}.jpg ja existe,
    le local. Caso contrario, faz Range fetch do CDN, salva no cache.
    """
    uf = uf.upper().strip()
    if uf not in VALID_UFS:
        raise PhotoNotFound(f"UF invalida: {uf}")

    cache_path = CACHE_DIR / uf / f"{sq_candidato}.jpg"
    if cache_path.is_file():
        return cache_path.read_bytes()

    # Miss — busca no CDN. Lock por UF garante que so 1 thread fala com o
    # handle compartilhado por vez (zipfile.ZipFile nao e thread-safe).
    log.info("tse_photos_fetch", uf=uf, sq=sq_candidato)
    target = f"F{uf}{sq_candidato}_div.jpg"
    lock = _get_lock(uf)

    with lock:
        # Recheck cache dentro do lock — outra thread pode ter buscado a
        # mesma foto enquanto esperavamos.
        if cache_path.is_file():
            return cache_path.read_bytes()

        handle = _get_handle(uf)
        try:
            data = handle.read(target)
        except KeyError:
            raise PhotoNotFound(
                f"Foto nao encontrada no zip {uf}: esperava {target}"
            ) from None
        except Exception as exc:
            # Erro de rede (ProtocolError, IncompleteRead, etc) — handle TCP
            # pode estar corrompido. Recria e tenta uma unica vez.
            log.warning(
                "tse_photos_retry",
                uf=uf,
                sq=sq_candidato,
                error=type(exc).__name__,
                msg=str(exc)[:200],
            )
            handle = _get_handle(uf, force_new=True)
            try:
                data = handle.read(target)
            except KeyError:
                raise PhotoNotFound(
                    f"Foto nao encontrada no zip {uf}: esperava {target}"
                ) from None

    # Persiste no cache (fora do lock — apenas IO local)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_path.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.rename(cache_path)
    log.info("tse_photos_cached", uf=uf, sq=sq_candidato, bytes=len(data))

    return data
