"""
Google Calendar — integração READ-ONLY, por usuário.

Fluxo OAuth (Authorization Code):
  connect  -> URL de consentimento do Google (com state assinado = user/tenant)
  callback -> troca o code por tokens; guarda o refresh_token CRIPTOGRADO
  events   -> usa o refresh_token p/ pegar um access_token e ler a agenda

Tudo via httpx (sem SDK pesado). O refresh_token é cifrado com Fernet, cuja
chave deriva do JWT_SECRET_KEY (não guardamos token em claro no banco).

Desligado por padrão: sem GOOGLE_CLIENT_ID/SECRET, is_configured() = False e os
endpoints respondem 'não configurado'.
"""
from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.config.settings import get_settings

_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN = "https://oauth2.googleapis.com/token"
_USERINFO = "https://www.googleapis.com/oauth2/v3/userinfo"
_EVENTS = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
_SCOPE = "openid email https://www.googleapis.com/auth/calendar.readonly"


def is_configured() -> bool:
    s = get_settings()
    return bool(s.GOOGLE_CLIENT_ID and s.GOOGLE_CLIENT_SECRET and s.GOOGLE_REDIRECT_URI)


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(
        hashlib.sha256(get_settings().JWT_SECRET_KEY.encode()).digest()
    )
    return Fernet(key)


def encrypt(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()


def decrypt(blob: str) -> str | None:
    try:
        return _fernet().decrypt(blob.encode()).decode()
    except (InvalidToken, Exception):
        return None


def auth_url(state: str) -> str:
    s = get_settings()
    params = {
        "client_id": s.GOOGLE_CLIENT_ID,
        "redirect_uri": s.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": _SCOPE,
        "access_type": "offline",   # garante refresh_token
        "prompt": "consent",        # força refresh_token mesmo em re-conexão
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{_AUTH}?{urlencode(params)}"


def exchange_code(code: str) -> dict:
    """Troca o authorization code por tokens. Retorna {refresh_token, access_token, email}."""
    s = get_settings()
    with httpx.Client(timeout=20) as c:
        r = c.post(_TOKEN, data={
            "code": code,
            "client_id": s.GOOGLE_CLIENT_ID,
            "client_secret": s.GOOGLE_CLIENT_SECRET,
            "redirect_uri": s.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
        r.raise_for_status()
        tok = r.json()
        access = tok.get("access_token")
        email = None
        if access:
            try:
                ui = c.get(_USERINFO, headers={"Authorization": f"Bearer {access}"})
                if ui.status_code == 200:
                    email = ui.json().get("email")
            except Exception:
                email = None
    return {
        "refresh_token": tok.get("refresh_token"),
        "access_token": access,
        "email": email,
    }


def _access_from_refresh(refresh_token: str) -> str | None:
    s = get_settings()
    try:
        with httpx.Client(timeout=20) as c:
            r = c.post(_TOKEN, data={
                "client_id": s.GOOGLE_CLIENT_ID,
                "client_secret": s.GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            })
            if r.status_code != 200:
                return None
            return r.json().get("access_token")
    except Exception:
        return None


def fetch_events(refresh_token: str, days_ahead: int = 60, days_back: int = 7) -> list[dict]:
    """Eventos do calendário principal entre (hoje - days_back) e (hoje + days_ahead)."""
    access = _access_from_refresh(refresh_token)
    if not access:
        return []
    now = datetime.now(timezone.utc)
    params = {
        "timeMin": (now - timedelta(days=days_back)).isoformat(),
        "timeMax": (now + timedelta(days=days_ahead)).isoformat(),
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": "100",
    }
    out: list[dict] = []
    try:
        with httpx.Client(timeout=25) as c:
            r = c.get(_EVENTS, params=params, headers={"Authorization": f"Bearer {access}"})
            if r.status_code != 200:
                return []
            for it in r.json().get("items", []):
                start = it.get("start", {})
                end = it.get("end", {})
                all_day = "date" in start
                starts_at = start.get("dateTime") or start.get("date")
                ends_at = end.get("dateTime") or end.get("date")
                if not starts_at:
                    continue
                out.append({
                    "google_id": it.get("id"),
                    "title": it.get("summary") or "(sem título)",
                    "description": it.get("description"),
                    "starts_at": starts_at,
                    "ends_at": ends_at,
                    "all_day": all_day,
                    "location": it.get("location"),
                    "html_link": it.get("htmlLink"),
                })
    except Exception:
        return []
    return out
