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

TENANT_SLUG="${TENANT_SLUG:-marenostrum-admin}"
TENANT_NAME="${TENANT_NAME:-MareNostrum Admin}"
# NAO usar TLD .local — email-validator do Pydantic rejeita (RFC 6761).
# Quando tiver dominio real (ex: marenostrum.com.br), troque aqui.
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@marenostrum.com.br}"
ADMIN_NAME="${ADMIN_NAME:-Administrador}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-MudeEss@Senha123}"

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
