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

# Cache de RemoteZip por UF: {uf: (handle, criado_em_epoch)}
_handles: dict[str, tuple[RemoteZip, float]] = {}
_handles_lock = threading.Lock()


def _zip_url(uf: str) -> str:
    return f"{CDN_BASE}/foto_cand2024_{uf}_div.zip"


def _get_handle(uf: str) -> RemoteZip:
    """Devolve RemoteZip pro UF (recria se expirado)."""
    now = time.monotonic()
    with _handles_lock:
        cached = _handles.get(uf)
        if cached is not None:
            handle, created = cached
            if now - created < _HANDLE_TTL_S:
                return handle
            # expirou — fecha e remove
            try:
                handle.close()
            except Exception:
                pass
            del _handles[uf]

        log.info("tse_photos_open_zip", uf=uf, url=_zip_url(uf))
        handle = RemoteZip(_zip_url(uf))
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

    # Miss — busca no CDN
    log.info("tse_photos_fetch", uf=uf, sq=sq_candidato)
    handle = _get_handle(uf)
    target = f"F{uf}{sq_candidato}_div.jpg"

    try:
        data = handle.read(target)
    except KeyError:
        # KeyError = arquivo nao existe no zip
        raise PhotoNotFound(
            f"Foto nao encontrada no zip {uf}: esperava {target}"
        ) from None

    # Persiste no cache
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    # Escrita atomica: tmp + rename
    tmp = cache_path.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.rename(cache_path)
    log.info("tse_photos_cached", uf=uf, sq=sq_candidato, bytes=len(data))

    return data
