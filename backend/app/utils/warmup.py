"""Auto-aquecimento do agg_cache logo após o startup.

Sem isso, o 1º usuário após cada restart paga ~3,4s no party-performance
(varre 8,7M votos). Como tudo no Painel/Partidos passa por essa agregação,
isso é o cold mais sentido.

Estratégia: spawna asyncio.task no lifespan startup → espera o app ficar
pronto → minta um token interno → bate nos endpoints via httpx em localhost.
Os endpoints populam o agg_cache normalmente. Não bloqueia readiness.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta

import httpx
import structlog

log = structlog.get_logger("marenostrum.warmup")

# Endpoints mais quentes — agg_cache. Lista ampliada cobrindo todos os
# cargos comuns + filtros tipicos (estado, eleitos-only).
WARM_PATHS: list[str] = [
    # Counts e KPIs do hub
    "/api/v1/tse/stats/counts",
    # Party performance — varios cargos
    "/api/v1/tse/stats/party-performance?year=2024&office_code=11",
    "/api/v1/tse/stats/party-performance?year=2024&office_code=13",
    "/api/v1/tse/stats/party-performance?year=2022&office_code=6",
    "/api/v1/tse/stats/party-performance?year=2022&office_code=7",
    # Winners map — varias eleicoes
    "/api/v1/tse/stats/winners-map?year=2024&office_code=11",
    "/api/v1/tse/stats/winners-map?year=2022&office_code=1",
    "/api/v1/tse/stats/winners-map?year=2022&office_code=3",
    # Top candidatos — variantes mais usadas no ranking nacional
    "/api/v1/tse/stats/top-candidates?year=2024&office_code=13&limit=50",
    "/api/v1/tse/stats/top-candidates?year=2024&office_code=11&limit=50",
    "/api/v1/tse/stats/top-candidates?year=2024&office_code=11&elected_only=true&limit=1",
    "/api/v1/tse/stats/top-candidates?year=2022&office_code=6&limit=50",
    "/api/v1/tse/stats/top-candidates?year=2022&office_code=7&limit=50",
    # Listagem geral de partidos (curta, mas chamada no GlobalSearch)
    "/api/v1/tse/parties",
    # Busca de bairros do censo (GlobalSearch): a 1ª chamada monta o índice
    # em memória (DISTINCT sobre ~200k setores, ~2,5s) — aquecido aqui,
    # a busca do usuário responde em milissegundos.
    "/api/v1/census/search-areas?q=centro",
]

# Re-aquece a cada 3.5h (DEFAULT_TTL=4h). Garante que o cache nunca expire
# entre rodadas — mesmo se o ultimo user visitou ha horas, o backend ja
# refrescou os endpoints quentes antes da expiracao.
REWARM_INTERVAL_S = 3.5 * 3600

# ---- Warmup do proxy_cache do nginx (censo) --------------------------------
# Os GeoJSON do censo são os "arquivos" mais pesados do app (Rio ~8MB).
# O nginx os cacheia 7d, mas o 1º MISS custa 4-6s. Aqui aquecemos via o
# listener interno :8088 — depois disso TODO usuário pega HIT (~0,2s).
# Chave do cache inclui Accept-Encoding → aquecemos as variantes reais
# de browser (Chrome/Edge/Opera/Firefox usam zstd; Safari não).
NGINX_WARM_BASE = "http://nginx:8088"
_BROWSER_ENCODINGS = ["gzip, deflate, br, zstd", "gzip, deflate, br"]


def _muni_top_warm_paths() -> list[str]:
    """Top-candidates dos 30 maiores municípios (por eleitorado) nos 2 combos
    que as telas Municípios e Bairros usam. Preenche o agg_cache — a query
    pesada (~1,5-6s fria em cidade grande) nunca chega no usuário."""
    from sqlalchemy import text as _text

    from app.core.database import SessionLocal

    try:
        with SessionLocal() as db:
            ids = db.execute(_text(
                "SELECT municipality_id FROM tse_municipality_electorate "
                "ORDER BY total DESC LIMIT 30"
            )).scalars().all()
    except Exception as e:  # pragma: no cover
        log.warning("warmup_muni_list_failed", err=str(e)[:160])
        return []
    out: list[str] = []
    for mid in ids:
        out.append(f"/api/v1/tse/municipalities/{mid}/top-candidates?office_code=11&limit=50")
        out.append(f"/api/v1/tse/municipalities/{mid}/top-candidates?office_code=13&limit=300")
    return out


def _census_warm_paths() -> list[str]:
    """TODOS os municípios com censo carregado (maiores primeiro — ficam
    quentes mais cedo) + uf-overview de cada UF presente. Dinâmico: ingerir
    uma UF nova entra no warmup sem mexer aqui."""
    from sqlalchemy import text as _text

    from app.core.database import SessionLocal

    try:
        with SessionLocal() as db:
            cds = db.execute(_text(
                "SELECT cd_mun FROM census_geo WHERE level='municipio' "
                "ORDER BY populacao DESC NULLS LAST LIMIT 120"
            )).scalars().all()
    except Exception as e:  # pragma: no cover
        log.warning("warmup_census_list_failed", err=str(e)[:160])
        return []
    ufs = sorted({str(cd)[:2] for cd in cds})
    return [f"/api/v1/census/uf-overview?uf={u}" for u in ufs] + [
        f"/api/v1/census/setores?cd_mun={cd}" for cd in cds
    ]


async def _warm_nginx_census(headers: dict) -> None:
    """Aquece o proxy_cache do nginx pros payloads do censo. Tolera falhas."""
    paths = _census_warm_paths()
    if not paths:
        return
    async with httpx.AsyncClient(base_url=NGINX_WARM_BASE, timeout=120.0) as c:
        for enc in _BROWSER_ENCODINGS:
            h = {**headers, "Accept-Encoding": enc}
            for path in paths:
                t0 = asyncio.get_event_loop().time()
                try:
                    r = await c.get(path, headers=h)
                    ms = int((asyncio.get_event_loop().time() - t0) * 1000)
                    log.info(
                        "warmup_nginx_ok", path=path, status=r.status_code,
                        ms=ms, cache=r.headers.get("x-cache-status", "?"),
                    )
                except Exception as e:  # pragma: no cover
                    log.warning("warmup_nginx_failed", path=path, err=str(e)[:160])


async def _warm_once() -> None:
    """Bate em todos os WARM_PATHS uma vez. Tolera falhas."""
    from app.core.database import SessionLocal
    from app.core.security import create_access_token
    from app.models.user import User

    with SessionLocal() as db:
        # Prefere um usuário com o módulo Censo liberado: o warm do
        # /census/search-areas só monta o índice se o flag estiver ativo.
        u = (
            db.query(User).filter(User.census_enabled.is_(True)).first()
            or db.query(User).first()
        )
        if u is None:
            log.warning("warmup_no_user_skip")
            return
        tok = create_access_token(
            user_id=u.id,
            tenant_id=u.tenant_id,
            role=u.role,
            # 15 min: a rodada inclui o warm do nginx (censo ~28 requests;
            # 1ª rodada pós-deploy pode levar 2-3 min nos MISS grandes).
            expires_delta=timedelta(minutes=15),
        )

    headers = {"Authorization": f"Bearer {tok}"}
    async with httpx.AsyncClient(
        base_url="http://localhost:8000", timeout=90.0
    ) as c:
        for path in WARM_PATHS + _muni_top_warm_paths():
            t0 = asyncio.get_event_loop().time()
            try:
                r = await c.get(path, headers=headers)
                ms = int((asyncio.get_event_loop().time() - t0) * 1000)
                log.info("warmup_ok", path=path, status=r.status_code, ms=ms)
            except Exception as e:  # pragma: no cover
                log.warning("warmup_path_failed", path=path, err=str(e)[:160])

    # Aquece também o cache de borda do nginx (GeoJSON do censo).
    await _warm_nginx_census(headers)


async def warm_up_cache(initial_delay: float = 3.0) -> None:
    """
    Loop continuo: warmup inicial -> sleep -> rewarm -> sleep -> ...
    Tolera falhas (loga e segue).
    """
    try:
        await asyncio.sleep(initial_delay)
        while True:
            try:
                await _warm_once()
                log.info("warmup_complete")
            except Exception as e:  # pragma: no cover
                log.warning("warmup_round_failed", err=str(e)[:200])
            await asyncio.sleep(REWARM_INTERVAL_S)
    except asyncio.CancelledError:
        log.info("warmup_cancelled")
        raise
    except Exception as e:  # pragma: no cover
        log.warning("warmup_aborted", err=str(e)[:200])
