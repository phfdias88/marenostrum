#!/usr/bin/env bash
# =============================================================================
# MareNostrum - Deploy idempotente na VPS Hostinger
# Uso: ./scripts/deploy.sh
# Rode como usuario 'deploy' (NUNCA root). Assumindo Docker ja instalado.
# =============================================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo "==> [1/5] Conferindo pre-requisitos..."
command -v docker >/dev/null || { echo "ERRO: docker nao instalado"; exit 1; }
docker compose version >/dev/null || { echo "ERRO: docker compose v2 nao instalado"; exit 1; }

echo "==> [2/5] Validando .env do backend..."
if [[ ! -f backend/.env ]]; then
    echo "ERRO: backend/.env nao existe. Copie de backend/.env.example e edite."
    exit 1
fi
# Garante que JWT_SECRET nao ficou no valor padrao
if grep -q "CHANGE_ME" backend/.env; then
    echo "ERRO: backend/.env ainda tem 'CHANGE_ME'. Gere segredo:"
    echo "       openssl rand -hex 32"
    exit 1
fi

echo "==> [3/5] Build das imagens (sem cache em mudancas de dep)..."
docker compose build --pull

echo "==> [4/5] Subindo stack..."
docker compose up -d --remove-orphans

echo "==> [5/5] Aguardando health da API..."
for i in {1..30}; do
    if curl -fsS http://localhost/api/health >/dev/null 2>&1; then
        echo "OK: API respondendo em http://localhost/api/health"
        echo ""
        echo "Acesse externamente:"
        echo "  Docs:   http://72.60.248.41/api/docs"
        echo "  Health: http://72.60.248.41/api/health"
        echo "  Web:    http://72.60.248.41/"
        exit 0
    fi
    sleep 2
done

echo "ERRO: API nao respondeu em 60s. Logs:"
docker compose logs --tail=50 api
exit 1
