"""
Rate limiting (anti-DoS) via slowapi.

Endpoints sensiveis (login, sync, /photo do TSE, busca) recebem limites
por IP. Sem isso, alguem pode disparar 1000 requests/seg e travar o backend
(o /photo destrava com IntersectionObserver no front, mas vetores diretos
via curl/script continuam abertos).

Storage: in-memory. A API roda com 1 worker uvicorn, entao o contador eh
consistente sem precisar de Redis. Se um dia escalar pra N workers, basta
trocar `storage_uri` por redis://.

Headers: lemos X-Forwarded-For (setado pelo nginx) pra pegar o IP REAL
do usuario, nao 127.0.0.1 do proxy.
"""
from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _real_ip(request: Request) -> str:
    """
    Le o IP real do cliente. Ordem de prioridade:
      1. X-Forwarded-For (primeiro IP da lista — nginx adiciona)
      2. X-Real-IP (nginx tambem seta)
      3. request.client.host (fallback)
    """
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        # X-Forwarded-For pode ser "client, proxy1, proxy2" — pegamos o 1o
        return xff.split(",")[0].strip()
    xri = request.headers.get("X-Real-IP", "")
    if xri:
        return xri.strip()
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
