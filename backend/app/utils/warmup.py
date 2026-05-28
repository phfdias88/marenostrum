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

# Endpoints mais quentes (Painel, Partidos, Mapa, Ranking)
WARM_PATHS: list[str] = [
    "/api/v1/tse/stats/counts",
    "/api/v1/tse/stats/party-performance?year=2024&office_code=11",
    "/api/v1/tse/stats/winners-map?year=2024&office_code=11",
    "/api/v1/tse/stats/top-candidates?year=2024&office_code=13&limit=50",
    "/api/v1/tse/stats/top-candidates?year=2024&office_code=11&limit=50",
]


async def warm_up_cache(initial_delay: float = 3.0) -> None:
    """Roda em background; tolera falhas (loga e segue)."""
    try:
        await asyncio.sleep(initial_delay)

        # Token interno (válido por 5 min — suficiente p/ aquecer)
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
            base_url="http://localhost:8000", timeout=60.0
        ) as c:
            for path in WARM_PATHS:
                t0 = asyncio.get_event_loop().time()
                try:
                    r = await c.get(path, headers=headers)
                    ms = int((asyncio.get_event_loop().time() - t0) * 1000)
                    log.info("warmup_ok", path=path, status=r.status_code, ms=ms)
                except Exception as e:  # pragma: no cover
                    log.warning("warmup_path_failed", path=path, err=str(e)[:160])

        log.info("warmup_complete")
    except Exception as e:  # pragma: no cover
        log.warning("warmup_aborted", err=str(e)[:200])
