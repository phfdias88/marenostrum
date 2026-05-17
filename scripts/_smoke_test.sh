#!/usr/bin/env bash
# Smoke test E2E pos-deploy: health -> login -> /me -> create -> list
set -euo pipefail

BASE="http://localhost"

echo "=== 1) Health"
curl -s $BASE/api/health
echo

echo "=== 2) Login"
LOGIN_RES=$(curl -s -X POST $BASE/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"tenant_slug":"marenostrum-admin","email":"admin@marenostrum.com.br","password":"MudeEss@Senha123"}')
TOKEN=$(echo "$LOGIN_RES" | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
echo "Token: ${TOKEN:0:50}..."

echo
echo "=== 3) /auth/me"
curl -s $BASE/api/v1/auth/me -H "Authorization: Bearer $TOKEN"

echo
echo
echo "=== 4) POST /contacts (criar Joao)"
curl -s -X POST $BASE/api/v1/contacts \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"full_name":"Joao Smoke Test","phone":"(32) 99999-9999","type":"voter","city":"Juiz de Fora","state":"MG"}'

echo
echo
echo "=== 5) GET /contacts (listar)"
curl -s "$BASE/api/v1/contacts?limit=5" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
