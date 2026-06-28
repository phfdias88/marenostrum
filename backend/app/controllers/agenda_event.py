"""
Controller da agenda parlamentar/campanha — CRUD tenant-scoped.

Listagem com filtro opcional `upcoming` (só futuros) e ordenação por
data. Geocoding é responsabilidade do cliente (lat/lng opcional).
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.core.dependencies import CurrentTenant
from app.core.security import create_access_token, decode_access_token
from app.models.agenda_event import AgendaEvent
from app.models.google_calendar_link import GoogleCalendarLink
from app.schemas.agenda_event import AgendaCreate, AgendaRead, AgendaUpdate
from app.utils import google_calendar as gcal

router = APIRouter(prefix="/agenda", tags=["agenda"])


@router.get("", response_model=list[AgendaRead], summary="Listar eventos da agenda")
def list_events(
    ctx: CurrentTenant,
    upcoming: bool = Query(False, description="Só eventos a partir de agora"),
    limit: int = Query(200, ge=1, le=500),
) -> list[AgendaRead]:
    stmt = select(AgendaEvent).where(AgendaEvent.tenant_id == ctx.tenant_id)
    if upcoming:
        stmt = stmt.where(AgendaEvent.starts_at >= datetime.now(timezone.utc))
    stmt = stmt.order_by(AgendaEvent.starts_at.asc()).limit(limit)
    rows = ctx.db.execute(stmt).scalars().all()
    return [AgendaRead.model_validate(r) for r in rows]


@router.post(
    "",
    response_model=AgendaRead,
    status_code=status.HTTP_201_CREATED,
    summary="Criar evento",
)
def create_event(payload: AgendaCreate, ctx: CurrentTenant) -> AgendaRead:
    e = AgendaEvent(tenant_id=ctx.tenant_id, **payload.model_dump())
    ctx.db.add(e)
    ctx.db.commit()
    ctx.db.refresh(e)
    return AgendaRead.model_validate(e)


@router.put("/{event_id}", response_model=AgendaRead, summary="Atualizar evento")
def update_event(
    event_id: UUID, payload: AgendaUpdate, ctx: CurrentTenant
) -> AgendaRead:
    e = ctx.db.get(AgendaEvent, event_id)
    if e is None or e.tenant_id != ctx.tenant_id:
        raise HTTPException(404, "Evento não encontrado")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(e, k, v)
    ctx.db.commit()
    ctx.db.refresh(e)
    return AgendaRead.model_validate(e)


@router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir evento",
)
def delete_event(event_id: UUID, ctx: CurrentTenant):
    e = ctx.db.get(AgendaEvent, event_id)
    if e is None or e.tenant_id != ctx.tenant_id:
        raise HTTPException(404, "Evento não encontrado")
    ctx.db.delete(e)
    ctx.db.commit()


# ===================== Google Calendar (read-only, por usuário) =====================

def _gcal_link(ctx: CurrentTenant) -> GoogleCalendarLink | None:
    return ctx.db.execute(
        select(GoogleCalendarLink).where(GoogleCalendarLink.user_id == ctx.user_id)
    ).scalar_one_or_none()


@router.get("/google/status", summary="Status da conexão com o Google Agenda")
def google_status(ctx: CurrentTenant) -> dict:
    link = _gcal_link(ctx)
    return {
        "configured": gcal.is_configured(),
        "connected": link is not None,
        "email": link.google_email if link else None,
    }


@router.get("/google/connect", summary="URL de autorização (read-only) do Google")
def google_connect(ctx: CurrentTenant) -> dict:
    if not gcal.is_configured():
        raise HTTPException(503, "Integração com o Google Agenda não configurada.")
    # state = token curto assinado com a identidade (validado no callback público).
    state = create_access_token(
        user_id=ctx.user_id, tenant_id=ctx.tenant_id, role="gcal_state",
        expires_delta=timedelta(minutes=10),
    )
    return {"url": gcal.auth_url(state)}


@router.get("/google/callback", include_in_schema=False)
def google_callback(request: Request, code: str | None = None, state: str | None = None):
    """Rota PÚBLICA — redirect do Google. Identidade vem do state assinado."""
    from app.core.database import SessionLocal

    dest = "/dashboard/agenda"
    if not code or not state:
        return RedirectResponse(f"{dest}?google=erro", status_code=302)
    try:
        claims = decode_access_token(state)
        user_id, tenant_id = claims.sub, claims.tid
    except Exception:
        return RedirectResponse(f"{dest}?google=erro", status_code=302)
    try:
        tok = gcal.exchange_code(code)
        refresh = tok.get("refresh_token")
        if not refresh:
            return RedirectResponse(f"{dest}?google=erro", status_code=302)
        with SessionLocal() as db:
            link = db.execute(
                select(GoogleCalendarLink).where(GoogleCalendarLink.user_id == user_id)
            ).scalar_one_or_none()
            if link is None:
                link = GoogleCalendarLink(user_id=user_id, tenant_id=tenant_id)
                db.add(link)
            link.refresh_token_enc = gcal.encrypt(refresh)
            link.google_email = tok.get("email")
            link.connected_at = datetime.now(timezone.utc)
            db.commit()
    except Exception:
        return RedirectResponse(f"{dest}?google=erro", status_code=302)
    return RedirectResponse(f"{dest}?google=ok", status_code=302)


@router.get("/google/events", summary="Eventos do Google Agenda do usuário")
def google_events(ctx: CurrentTenant, days: int = Query(60, ge=1, le=180)) -> list[dict]:
    link = _gcal_link(ctx)
    if link is None:
        return []
    refresh = gcal.decrypt(link.refresh_token_enc)
    if not refresh:
        return []
    return gcal.fetch_events(refresh, days_ahead=days)


@router.delete(
    "/google/disconnect",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desconectar o Google Agenda",
)
def google_disconnect(ctx: CurrentTenant):
    link = _gcal_link(ctx)
    if link is not None:
        ctx.db.delete(link)
        ctx.db.commit()
