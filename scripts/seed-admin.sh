#!/usr/bin/env bash
# =============================================================================
# Bootstrap rapido: cria tenant "MareNostrum Admin" + owner para o primeiro login.
# Idempotente — pode rodar varias vezes sem erro.
#
# Uso:
#   ./scripts/seed-admin.sh                       # usa valores default
#   ADMIN_PASSWORD='OutraSenh@' ./scripts/seed-admin.sh
# =============================================================================
set -euo pipefail

# cd pro project dir — permite chamar o script de qualquer lugar (CI, /tmp, etc)
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

TENANT_SLUG="${TENANT_SLUG:-marenostrum-admin}"
TENANT_NAME="${TENANT_NAME:-MareNostrum Admin}"
# NAO usar TLD .local — email-validator do Pydantic rejeita (RFC 6761).
# Quando tiver dominio real (ex: marenostrum.com.br), troque aqui.
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@marenostrum.com.br}"
ADMIN_NAME="${ADMIN_NAME:-Administrador}"

# SEGURANCA: em producao a senha TEM que ser passada explicitamente. Nada de
# default versionado (qualquer um que le o repo saberia a senha do owner).
if [ "${APP_ENV:-}" = "production" ] && [ -z "${ADMIN_PASSWORD:-}" ]; then
    echo "ERRO: em producao defina ADMIN_PASSWORD explicitamente." >&2
    echo "  Ex: ADMIN_PASSWORD='<senha-forte>' ./scripts/seed-admin.sh" >&2
    exit 1
fi
# Fora de producao (dev/CI local), gera uma aleatoria se nao informada — nunca
# uma senha fixa conhecida. Precisa de >=10 chars pra passar na politica.
ADMIN_PASSWORD="${ADMIN_PASSWORD:-Dev-$(head -c 9 /dev/urandom | base64 | tr -dc 'A-Za-z0-9')9}"

echo "==> Seed: tenant='${TENANT_SLUG}' admin='${ADMIN_EMAIL}'"

docker compose exec -T api python -m app.utils.seed \
    --tenant-slug "$TENANT_SLUG" \
    --tenant-name "$TENANT_NAME" \
    --email "$ADMIN_EMAIL" \
    --password "$ADMIN_PASSWORD" \
    --name "$ADMIN_NAME"

echo ""
echo "Login no frontend com:"
echo "  Campanha (slug): $TENANT_SLUG"
echo "  Email:           $ADMIN_EMAIL"
echo "  Senha:           $ADMIN_PASSWORD"
echo ""
echo "AVISO: troque a senha padrao em producao!"
