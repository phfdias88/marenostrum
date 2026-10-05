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

echo "==> [2/5] Validando .env files..."
# .env da raiz: vars de build do Next.js (NEXT_PUBLIC_*)
if [[ ! -f .env ]]; then
    echo "ERRO: .env (raiz) nao existe. Copie de .env.example e ajuste."
    echo "      cp .env.example .env && nano .env"
    exit 1
fi
# .env do backend: secrets de runtime (JWT, Postgres)
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

echo "==> [3/6] Build das imagens (sem cache em mudancas de dep)..."
docker compose build --pull

echo "==> [4/6] Dump de seguranca PRE-MIGRACAO (best-effort)..."
# O entrypoint da API roda 'alembic upgrade head' no boot. Uma migration com
# bug pode corromper/crashar sem rollback. Tiramos um dump ANTES de subir a
# nova imagem — se o db ja estiver de pe (redeploy). No 1o deploy (sem db/dados)
# simplesmente pula. Nao aborta o deploy se falhar.
BACKUP_DIR=/home/deploy/backups
mkdir -p "$BACKUP_DIR" 2>/dev/null || true
pre="$BACKUP_DIR/pre-migrate_$(date +%F_%H%M%S).dump"
if docker compose exec -T db pg_dump -U marenostrum -d marenostrum -Fc > "${pre}.part" 2>/dev/null \
   && [ "$(head -c 5 "${pre}.part" 2>/dev/null)" = "PGDMP" ]; then
    mv "${pre}.part" "$pre"
    echo "    dump pre-migracao: $pre ($(( $(stat -c %s "$pre")/1024/1024 ))MB)"
    # mantem os 3 pre-migrate mais recentes
    ls -1t "$BACKUP_DIR"/pre-migrate_*.dump 2>/dev/null | tail -n +4 | xargs -r rm -f || true
else
    rm -f "${pre}.part" 2>/dev/null || true
    echo "    (sem dump — db ainda nao esta de pe; provavelmente 1o deploy)"
fi

echo "==> [5/6] Subindo stack..."
docker compose up -d --remove-orphans

echo "==> Limpando imagens dangling e build cache (reclaim de disco)..."
docker image prune -f || true
docker builder prune -f || true

echo "==> [6/6] Aguardando health da API..."
for i in {1..30}; do
    if curl -fsS http://localhost/api/health >/dev/null 2>&1; then
        echo "OK: API respondendo em http://localhost/api/health"
        # Purga o cache de borda APOS o deploy subir saudavel — senao respostas
        # antigas de /tse e /census ficam servidas por ate 7 dias e o deploy
        # "some" (gotcha conhecido). Rodar so no sucesso evita limpar cache de
        # um deploy que nem subiu.
        docker compose exec -T nginx sh -c 'rm -rf /var/cache/nginx/census/* /var/cache/nginx/tse/*' 2>/dev/null || true
        echo "OK: cache de borda (census/tse) limpo — deploy visivel na hora"
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
