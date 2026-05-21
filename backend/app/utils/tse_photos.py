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

def _cdn_base(year: int) -> str:
    return f"https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes{year}/fotos"

CACHE_DIR = Path("/var/marenostrum/tse_photos")

# TTL do RemoteZip handle (central directory cacheado).
# Apos isso, recriamos pra liberar memoria e pegar updates do CDN.
_HANDLE_TTL_S = 3600  # 1h

# UFs validas (defensivo — evita SSRF caso state malformado chegue)
# BR = candidatos nacionais (presidente 2022).
VALID_UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
    "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
    "RS", "RO", "RR", "SC", "SP", "SE", "TO", "BR",
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


def _zip_url(uf: str, year: int) -> str:
    return f"{_cdn_base(year)}/foto_cand{year}_{uf}_div.zip"


def _get_lock(key: str) -> threading.Lock:
    with _dict_lock:
        lock = _handle_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _handle_locks[key] = lock
        return lock


def _get_handle(uf: str, year: int, *, force_new: bool = False) -> RemoteZip:
    """
    Devolve RemoteZip pro (year, uf). Cache keyed por 'year_uf'.
    DEVE ser chamado com o lock ja adquirido.
    """
    key = f"{year}_{uf}"
    now = time.monotonic()
    with _dict_lock:
        cached = _handles.get(key)
        if cached is not None and not force_new:
            handle, created = cached
            if now - created < _HANDLE_TTL_S:
                return handle
        if cached is not None:
            try:
                cached[0].close()
            except Exception:
                pass
            _handles.pop(key, None)

    log.info("tse_photos_open_zip", key=key, url=_zip_url(uf, year), force_new=force_new)
    handle = RemoteZip(_zip_url(uf, year))
    with _dict_lock:
        _handles[key] = (handle, now)
    return handle


# --------------------------------------------------------- API publica


class PhotoNotFound(Exception):
    """Candidato nao tem foto registrada no TSE pra esse UF."""


def get_candidate_photo(uf: str, sq_candidato: int, year: int = 2024) -> bytes:
    """
    Retorna bytes JPEG da foto do candidato. Levanta PhotoNotFound se nao existir.

    Cache em disco: /var/marenostrum/tse_photos/{year}/{UF}/{SQ}.jpg.
    Caso contrario, faz Range fetch do zip do CDN do ano correto, salva.
    """
    uf = uf.upper().strip()
    if uf not in VALID_UFS:
        raise PhotoNotFound(f"UF invalida: {uf}")

    cache_path = CACHE_DIR / str(year) / uf / f"{sq_candidato}.jpg"
    if cache_path.is_file():
        return cache_path.read_bytes()

    # Miss — busca no CDN. Lock por (year,uf) garante que so 1 thread fala com
    # o handle compartilhado por vez (zipfile.ZipFile nao e thread-safe).
    log.info("tse_photos_fetch", uf=uf, sq=sq_candidato, year=year)
    # TSE mistura .jpg e .jpeg dentro do mesmo zip (ex: 2022) — tenta ambos.
    targets = [f"F{uf}{sq_candidato}_div.jpg", f"F{uf}{sq_candidato}_div.jpeg"]
    lock = _get_lock(f"{year}_{uf}")

    def _read_any(handle: RemoteZip) -> bytes | None:
        for t in targets:
            try:
                return handle.read(t)
            except KeyError:
                continue
        return None

    with lock:
        if cache_path.is_file():
            return cache_path.read_bytes()

        handle = _get_handle(uf, year)
        try:
            data = _read_any(handle)
        except Exception as exc:
            log.warning(
                "tse_photos_retry",
                uf=uf, sq=sq_candidato, year=year,
                error=type(exc).__name__, msg=str(exc)[:200],
            )
            handle = _get_handle(uf, year, force_new=True)
            data = _read_any(handle)

        if data is None:
            raise PhotoNotFound(
                f"Foto nao encontrada no zip {year}/{uf}: {targets}"
            )

    # Persiste no cache (fora do lock — apenas IO local)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_path.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.rename(cache_path)
    log.info("tse_photos_cached", uf=uf, sq=sq_candidato, year=year, bytes=len(data))

    return data
