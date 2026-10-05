#!/usr/bin/env python3
"""
Atualiza a lista de senadores em exercicio (partido de hoje) a partir dos dados
abertos do Senado. E o que a tela da bancada usa em "no mandato".

Quando rodar: depois de troca de partido relevante, de posse de suplente, e
sempre antes de mostrar a bancada num evento. A lista muda pouco; nao precisa
de cron apertado.

USO (entra por stdin, como os outros scripts de operacao):
    docker compose exec -T -e PYTHONPATH=/app api \
        python - < backend/scripts/atualizar_senado.py
"""
from __future__ import annotations

import collections

import httpx

from app.core.database import SessionLocal
from app.services import senado


def main() -> int:
    r = httpx.get(
        senado.URL_EM_EXERCICIO, timeout=60, follow_redirects=True,
        headers={"Accept": "application/json",
                 "User-Agent": "Mozilla/5.0 (MareNostrum; bancada do Senado)"},
    )
    r.raise_for_status()
    itens = senado.ler_lista(r.json())

    db = SessionLocal()
    try:
        total = senado.gravar(db, itens)
    finally:
        db.close()

    por_fim = collections.Counter(str(i["term_end"]) for i in itens)
    print(f"senadores gravados: {total} | fim do mandato: {dict(por_fim)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
