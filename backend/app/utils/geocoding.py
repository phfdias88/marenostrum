"""
Cliente Nominatim (OpenStreetMap) com rate limit honesto.

POR QUE este modulo existe:
- Nominatim e gratuito mas exige (a) User-Agent identificavel, (b) <= 1 req/s
  por IP. Ignorar isso = bloqueio do nosso IP.
- Por isso aqui temos um Lock asyncio + timestamp do ultimo request, garantindo
  >= 1.0s entre chamadas mesmo sob alta concorrencia.

POR QUE usamos httpx.AsyncClient + BackgroundTasks (no service):
- Geocoding NAO bloqueia a resposta do POST/PUT do contato — o cliente recebe
  201 imediato e o lat/lng aparece silenciosamente quando o background termina.
- Se Nominatim cair ou demorar, UX nao e afetada.

POR QUE a background task abre nova sessao DB:
- A sessao do request original ja foi fechada quando a task roda.
- SessionLocal cria conexao propria, faz update, fecha.
"""
import asyncio
import time
from uuid import UUID

import httpx
import structlog
from sqlalchemy import update

from app.config import get_settings
from app.core.database import SessionLocal
from app.models.contact import Contact

log = structlog.get_logger("marenostrum.geocoding")

# Estado de rate limit a NIVEL DE PROCESSO (Lock + timestamp).
# Em deploy multi-worker (nao e nosso caso — workers=1), use Redis.
_rate_lock = asyncio.Lock()
_last_request_at: float = 0.0
_MIN_INTERVAL_S = 1.0


# ----------------------------------------------------------------- helpers


def _build_query(
    *,
    address: str | None,
    neighborhood: str | None,
    city: str,
    state: str,
) -> str:
    """Monta string de busca: 'rua X, bairro Y, Cidade, UF, Brasil'."""
    parts = [p for p in [address, neighborhood, city, state] if p]
    parts.append("Brasil")
    return ", ".join(parts)


async def _throttle() -> None:
    """Garante >= 1s entre chamadas a Nominatim (politica de uso)."""
    global _last_request_at
    async with _rate_lock:
        now = time.monotonic()
        wait = _last_request_at + _MIN_INTERVAL_S - now
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_at = time.monotonic()


# ----------------------------------------------------------------- public


async def geocode(query: str) -> tuple[float, float] | None:
    """
    Converte string de endereco em (lat, lng).
    Retorna None se nada encontrado, ou em qualquer erro (loga warning).
    """
    settings = get_settings()
    await _throttle()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{settings.NOMINATIM_BASE_URL}/search",
                params={
                    "q": query,
                    "format": "json",
                    "limit": 1,
                    "addressdetails": 0,
                },
                headers={"User-Agent": settings.NOMINATIM_USER_AGENT},
            )
            r.raise_for_status()
            data = r.json()
            if not data:
                log.info("geocode_no_results", query=query)
                return None
            first = data[0]
            return float(first["lat"]), float(first["lon"])
    except httpx.HTTPError as exc:
        log.warning("geocode_http_error", query=query, error=str(exc))
        return None
    except (KeyError, ValueError) as exc:
        log.warning("geocode_parse_error", query=query, error=str(exc))
        return None


async def geocode_and_persist_contact(
    *,
    contact_id: UUID,
    tenant_id: UUID,
    address: str | None,
    neighborhood: str | None,
    city: str | None,
    state: str | None,
) -> None:
    """
    Background task: geocoda um contato e salva lat/lng no banco.
    Tenant_id obrigatorio no WHERE — defesa multi-tenant tambem aqui.
    """
    if not address and not neighborhood:
        log.info("geocode_skipped", reason="no_address", contact_id=str(contact_id))
        return

    settings = get_settings()
    query = _build_query(
        address=address,
        neighborhood=neighborhood,
        city=city or settings.GEOCODING_DEFAULT_CITY,
        state=state or settings.GEOCODING_DEFAULT_STATE,
    )

    coords = await geocode(query)
    if coords is None:
        return

    lat, lng = coords
    # Abre sessao propria — a sessao do request ja fechou
    with SessionLocal() as db:
        stmt = (
            update(Contact)
            .where(Contact.id == contact_id, Contact.tenant_id == tenant_id)
            .values(latitude=lat, longitude=lng)
        )
        result = db.execute(stmt)
        db.commit()
        log.info(
            "geocode_persisted",
            contact_id=str(contact_id),
            tenant_id=str(tenant_id),
            lat=lat,
            lng=lng,
            rows=result.rowcount,
        )
