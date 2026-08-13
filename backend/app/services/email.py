"""
E-mail transacional (SMTP do domínio).

Fallback seguro: se o SMTP não estiver configurado (dev/staging, ou antes de
receber as credenciais do @marenostrumconsult), NÃO quebra — apenas LOGA o
conteúdo (incluindo o link), pra dev/testes. Em produção, preenche SMTP_* no
.env e o envio real liga sozinho.

Nunca levanta exceção pro caller: e-mail que falha vira log de erro, não derruba
o fluxo (ex.: o webhook do Asaas não pode falhar por causa de e-mail).
"""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

import structlog

from app.config import get_settings

log = structlog.get_logger("marenostrum.email")


def send_email(*, to: str, subject: str, text: str, html: str | None = None) -> bool:
    """Envia um e-mail. Retorna True se saiu pelo SMTP, False se logou (fallback)
    ou falhou. Nunca levanta."""
    s = get_settings()
    if not (s.SMTP_HOST and s.SMTP_FROM):
        # SMTP desligado: loga (dev/staging) — o link fica visível no log.
        log.warning("email_smtp_disabled_logging_only", to=to, subject=subject, body=text)
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = s.SMTP_FROM
    msg["To"] = to
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")

    try:
        with smtplib.SMTP(s.SMTP_HOST, s.SMTP_PORT, timeout=15) as smtp:
            if s.SMTP_STARTTLS:
                smtp.starttls(context=ssl.create_default_context())
            if s.SMTP_USER:
                smtp.login(s.SMTP_USER, s.SMTP_PASSWORD or "")
            smtp.send_message(msg)
        log.info("email_sent", to=to, subject=subject)
        return True
    except Exception as exc:  # noqa: BLE001 — e-mail nunca derruba o fluxo
        log.error("email_send_failed", to=to, subject=subject, error=str(exc))
        return False


def send_set_password_email(*, to: str, name: str, link: str) -> bool:
    """E-mail com o link de definição de senha do acesso recém-comprado."""
    subject = "Seu acesso ao MareNostrum · defina sua senha"
    text = (
        f"Olá, {name}!\n\n"
        "Seu pagamento foi confirmado e seu acesso ao B.I. Eleitoral Completo já "
        "está pronto.\n\n"
        f"Defina sua senha e entre por este link (expira em 72 horas):\n{link}\n\n"
        "Depois de definir a senha, você acessa o sistema normalmente.\n\n"
        "Equipe MareNostrum"
    )
    html = (
        f"<p>Olá, <strong>{name}</strong>!</p>"
        "<p>Seu pagamento foi confirmado e seu acesso ao <strong>B.I. Eleitoral "
        "Completo</strong> já está pronto.</p>"
        f'<p><a href="{link}">Clique aqui para definir sua senha e entrar</a> '
        "(o link expira em 72 horas).</p>"
        "<p>Equipe MareNostrum</p>"
    )
    return send_email(to=to, subject=subject, text=text, html=html)
