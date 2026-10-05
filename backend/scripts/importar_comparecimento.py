#!/usr/bin/env python3
"""
Importa comparecimento, abstencao, brancos e nulos das eleicoes JA FECHADAS.

Fonte: `detalhe_votacao_munzona_<ano>.zip`, do portal de dados abertos do TSE
(uns 4 MB por ano). A eleicao em apuracao nao passa por aqui — o canal ao vivo
grava a mesma tabela a cada passada (scripts/apuracao_ao_vivo.py).

Idempotente: reexecutar SUBSTITUI as linhas do ano, nao soma.

USO (o script mora no host e entra por stdin, para sobreviver a deploy):
    docker compose exec -T -e PYTHONPATH=/app api \
        python - --anos 2018,2022 < backend/scripts/importar_comparecimento.py
"""
from __future__ import annotations

import argparse
import sys

import structlog

from app.core.database import SessionLocal
from app.services.comparecimento import importar_detalhe
from app.utils.tse_sync import CACHE_DIR, TSE_BASE_URL, download_zip

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        structlog.dev.ConsoleRenderer(colors=False),
    ],
    logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
    cache_logger_on_first_use=True,
)
log = structlog.get_logger("tse.comparecimento")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--anos", required=True, help="anos separados por virgula")
    args = p.parse_args()
    anos = [int(a) for a in args.anos.split(",") if a.strip().isdigit()]

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    try:
        for ano in anos:
            destino = CACHE_DIR / f"detalhe_votacao_munzona_{ano}.zip"
            url = (
                f"{TSE_BASE_URL}/detalhe_votacao_munzona/"
                f"detalhe_votacao_munzona_{ano}.zip"
            )
            download_zip(url, destino, max_mb=60)
            resumo = importar_detalhe(db, destino, ano=ano)
            log.info("ano_pronto", ano=ano, **resumo)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
