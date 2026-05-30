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
]

# Re-aquece a cada 3.5h (DEFAULT_TTL=4h). Garante que o cache nunca expire
# entre rodadas — mesmo se o ultimo user visitou ha horas, o backend ja
# refrescou os endpoints quentes antes da expiracao.
REWARM_INTERVAL_S = 3.5 * 3600


async def _warm_once() -> None:
    """Bate em todos os WARM_PATHS uma vez. Tolera falhas."""
    from app.core.database import SessionLocal
    from app.core.security import create_access_token
    from app.models.user import User

    with SessionLocal() as db:
        u = db.query(User).first()
        if u is None:
            log.warning("warmup_no_user_skip")
            return
        tok = create_access_token(
            user_id=u.id,
            tenant_id=u.tenant_id,
            role=u.role,
            expires_delta=timedelta(minutes=5),
        )

    headers = {"Authorization": f"Bearer {tok}"}
    async with httpx.AsyncClient(
        base_url="http://localhost:8000", timeout=90.0
    ) as c:
        for path in WARM_PATHS:
            t0 = asyncio.get_event_loop().time()
            try:
                r = await c.get(path, headers=headers)
                ms = int((asyncio.get_event_loop().time() - t0) * 1000)
                log.info("warmup_ok", path=path, status=r.status_code, ms=ms)
            except Exception as e:  # pragma: no cover
                log.warning("warmup_path_failed", path=path, err=str(e)[:160])


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
