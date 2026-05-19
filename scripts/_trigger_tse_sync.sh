#!/usr/bin/env bash
# Login -> POST /tse/sync -> show job id
set -e

EMAIL="${ADMIN_EMAIL:-admin@marenostrum.com.br}"
PASSWORD="${ADMIN_PASSWORD:-MudeEss@Senha123}"
SLUG="${TENANT_SLUG:-marenostrum-admin}"
API="http://localhost/api/v1"

echo "== Login =="
TOKEN=$(curl -fsS -X POST "$API/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"tenant_slug\":\"$SLUG\",\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "Token: ${TOKEN:0:40}..."

echo ""
echo "== POST /tse/sync?dataset=candidato_munzona_2024 =="
curl -fsS -X POST "$API/tse/sync?dataset=candidato_munzona_2024" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
