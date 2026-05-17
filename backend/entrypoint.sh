#!/bin/sh
# Entrypoint: roda migrations e depois inicia o uvicorn.
# Idempotente — `alembic upgrade head` nao faz nada se ja estiver atualizado.
set -e

echo "==> Aplicando migrations..."
alembic upgrade head

echo "==> Iniciando API..."
exec "$@"
