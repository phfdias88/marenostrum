#!/usr/bin/env python3
"""
Vigia de disponibilidade — avisa por e-mail quando algo sai do ar.

MOTIVO (incidente jul/2026): o domínio saiu da Vercel e o sistema ficou
inacessível por horas; só descobrimos quando o sócio reclamou no WhatsApp.
Este script troca "reclamação do cliente" por "alerta automático".

COMO PENSA:
- Checa cada alvo N vezes (uma falha isolada de rede não vira alerta).
- Só manda e-mail na MUDANÇA de estado: OK->FORA (alerta) e FORA->OK
  (recuperado). Sem isso, um problema de 1 dia viraria 288 e-mails.
- Guarda o estado em disco entre execuções.

USO (cron, a cada 5 min):
  */5 * * * * cd /home/deploy/marenostrum && python3 scripts/monitor_uptime.py >> /var/log/mn-monitor.log 2>&1
"""
from __future__ import annotations

import json
import os
import smtplib
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
STATE_FILE = BASE / ".monitor-state.json"
ENV_FILE = BASE / "backend" / ".env"

# Para quem vão os alertas (separe por vírgula em ALERT_EMAILS no .env).
DEFAULT_ALERTS = "phfdias88@gmail.com"

# Alvos monitorados. `critical` entra no assunto do e-mail.
TARGETS = [
    {
        "name": "Sistema (servidor direto)",
        "url": "https://srv1412083.hstgr.cloud/sistema/login",
        "expect": 200,
        "critical": True,
    },
    {
        "name": "API do sistema (health)",
        "url": "https://srv1412083.hstgr.cloud/sistema/api/health",
        "expect": 200,
        "critical": True,
    },
    {
        "name": "Site no domínio",
        "url": "https://marenostrumconsult.com.br/",
        "expect": 200,
        "critical": False,
    },
    {
        "name": "Login no domínio",
        "url": "https://marenostrumconsult.com.br/sistema/login",
        "expect": 200,
        "critical": True,
    },
]

TRIES = 3          # tentativas antes de declarar FORA
TIMEOUT = 20       # segundos por tentativa


def load_env() -> dict:
    """Lê o .env do backend (SMTP já configurado lá) sem depender de libs."""
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def check(target: dict) -> tuple[bool, str]:
    """True se respondeu o esperado em alguma tentativa."""
    last = ""
    for attempt in range(TRIES):
        try:
            req = urllib.request.Request(
                target["url"], headers={"User-Agent": "mn-monitor/1.0"}
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                if r.status == target["expect"]:
                    return True, f"HTTP {r.status}"
                last = f"HTTP {r.status} (esperado {target['expect']})"
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code} (esperado {target['expect']})"
        except Exception as e:  # noqa: BLE001 — rede: qualquer erro é "fora"
            last = f"{type(e).__name__}"
        if attempt < TRIES - 1:
            time.sleep(3)
    return False, last


def send_email(env: dict, subject: str, body: str) -> None:
    host = env.get("SMTP_HOST")
    user = env.get("SMTP_USER")
    pwd = env.get("SMTP_PASSWORD")
    if not (host and user and pwd):
        print("[monitor] SMTP não configurado — alerta só no log")
        return
    to = [e.strip() for e in env.get("ALERT_EMAILS", DEFAULT_ALERTS).split(",") if e.strip()]
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = env.get("SMTP_FROM", user)
    msg["To"] = ", ".join(to)
    msg.set_content(body)
    port = int(env.get("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=30) as s:
        if env.get("SMTP_STARTTLS", "true").lower() != "false":
            s.starttls(context=ssl.create_default_context())
        s.login(user, pwd)
        s.send_message(msg)
    print(f"[monitor] alerta enviado para {', '.join(to)}")


def main() -> int:
    env = load_env()
    prev = {}
    if STATE_FILE.exists():
        try:
            prev = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — estado corrompido: recomeça limpo
            prev = {}

    agora = datetime.now(timezone.utc).astimezone()
    now_state, caiu, voltou = {}, [], []

    for t in TARGETS:
        ok, detail = check(t)
        now_state[t["name"]] = ok
        antes = prev.get(t["name"])
        marca = "OK  " if ok else "FORA"
        print(f"[monitor] {agora:%d/%m %H:%M} {marca} {t['name']} — {detail}")
        if antes is True and not ok:
            caiu.append((t, detail))
        elif antes is False and ok:
            voltou.append((t, detail))

    STATE_FILE.write_text(json.dumps(now_state, indent=2), encoding="utf-8")

    if caiu:
        crit = any(t["critical"] for t, _ in caiu)
        subject = ("[URGENTE] " if crit else "[aviso] ") + "MareNostrum fora do ar: " + \
                  ", ".join(t["name"] for t, _ in caiu)
        linhas = [f"Detectado em {agora:%d/%m/%Y %H:%M}", ""]
        linhas += [f"FORA: {t['name']}\n  {t['url']}\n  {d}" for t, d in caiu]
        linhas += [
            "",
            "O que costuma ser:",
            "- Só o DOMÍNIO fora e o servidor OK -> problema de DNS/hospedagem do site.",
            "- Tudo fora -> VPS caiu (verificar no painel da Hostinger).",
            "",
            "Acesso alternativo enquanto isso:",
            "  https://srv1412083.hstgr.cloud/sistema/login",
        ]
        send_email(env, subject, "\n".join(linhas))

    if voltou:
        subject = "[ok] MareNostrum voltou: " + ", ".join(t["name"] for t, _ in voltou)
        body = f"Recuperado em {agora:%d/%m/%Y %H:%M}\n\n" + "\n".join(
            f"OK: {t['name']} — {d}" for t, d in voltou
        )
        send_email(env, subject, body)

    return 0


if __name__ == "__main__":
    sys.exit(main())
