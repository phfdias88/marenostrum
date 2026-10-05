"""
Rate limiting (anti-DoS) via slowapi.

Endpoints sensiveis (login, sync, /photo do TSE, busca) recebem limites
por IP. Sem isso, alguem pode disparar 1000 requests/seg e travar o backend
(o /photo destrava com IntersectionObserver no front, mas vetores diretos
via curl/script continuam abertos).

Storage: in-memory. A API roda com 1 worker uvicorn, entao o contador eh
consistente sem precisar de Redis. Se um dia escalar pra N workers, basta
trocar `storage_uri` por redis://.

IP real do cliente: confiamos SOMENTE em headers que o nginx sobrescreve,
nunca no que o cliente manda.
"""
from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _real_ip(request: Request) -> str:
    """
    Le o IP real do cliente de forma NAO-FORJAVEL.

    IMPORTANTE (correcao de seguranca): o `X-Forwarded-For` que chega na app e
    `"<xff_do_cliente>, <ip_real>"` — o nginx APENDA o IP real ao que o cliente
    mandou (`$proxy_add_x_forwarded_for`). Pegar o PRIMEIRO item deixava o
    atacante escolher o proprio identificador de rate limit: bastava variar o
    header a cada request pra zerar o contador e fazer brute force ilimitado no
    /auth/login. Por isso:
      1. X-Real-IP  — o nginx faz `proxy_set_header X-Real-IP $remote_addr`, que
         SOBRESCREVE qualquer valor do cliente. E a fonte confiavel.
      2. ULTIMO item do X-Forwarded-For — o IP que o nginx apendou (o real);
         os itens anteriores sao controlados pelo cliente e ignorados.
      3. request.client.host (fallback quando nao ha proxy — dev local).
    """
    xri = request.headers.get("X-Real-IP", "")
    if xri:
        return xri.strip()
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        # Ultimo item = o que o proxy da nossa borda apendou (nao-forjavel).
        return xff.split(",")[-1].strip()
    return get_remote_address(request)


limiter = Limiter(
    key_func=_real_ip,
    # Default global: bem permissivo, so existe pra cair bem em ataques DDoS
    # massivos. Cada endpoint sensivel define seu proprio limite menor.
    default_limits=["600/minute"],
    # headers_enabled=True quebra endpoints que retornam Response direto
    # (photo, dossier PDF) — slowapi tenta injetar X-RateLimit-* mas a
    # resposta nao e starlette.Response. Mantemos os headers via slowapi
    # middleware automatico quando aplicavel.
    headers_enabled=False,
)
