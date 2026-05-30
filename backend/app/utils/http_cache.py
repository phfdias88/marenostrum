"""
Helpers HTTP cache: Cache-Control + ETag.

Dados TSE historicos sao publicos e imutaveis entre syncs — vale cachear
no browser por horas. Cache-Control com max-age + stale-while-revalidate
permite que o browser sirva instantaneamente do cache enquanto refaz a
request no fundo. ETag opcional permite curtos-circuitos 304 quando o
backend ja sabe que o conteudo nao mudou.

Uso simples:

    @router.get(...)
    def some(response: Response, ...):
        set_public_cache(response, max_age=3600, swr=86400)
        return ...

ou pra endpoints que devolvem Response cru, usar `cache_headers(...)` e
mesclar manualmente nos headers.
"""
from __future__ import annotations

from fastapi import Response


def set_public_cache(
    response: Response,
    *,
    max_age: int = 3600,
    swr: int = 86400,
    private: bool = False,
) -> None:
    """Marca a resposta como cacheavel por max_age segundos + stale-while-revalidate.

    Args:
        max_age: tempo "fresco" — browser/nginx usam direto, sem request.
        swr: depois de max_age, browser usa stale por mais swr segundos
            enquanto valida no background. Total = max_age + swr.
        private: True = so cache do navegador. False = nginx pode cachear.
    """
    visibility = "private" if private else "public"
    response.headers["Cache-Control"] = (
        f"{visibility}, max-age={max_age}, stale-while-revalidate={swr}"
    )


def cache_headers(
    *, max_age: int = 3600, swr: int = 86400, etag: str | None = None
) -> dict[str, str]:
    """Mesma logica, retorna dict pra mesclar com Response(headers=...)."""
    h = {"Cache-Control": f"public, max-age={max_age}, stale-while-revalidate={swr}"}
    if etag:
        h["ETag"] = f'W/"{etag}"'
    return h
