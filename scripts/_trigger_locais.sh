#!/usr/bin/env bash
set -e
API="http://localhost/api/v1"
TOKEN=$(curl -fsS -X POST "$API/auth/login" -H "Content-Type: application/json" \
  -d '{"tenant_slug":"marenostrum-admin","email":"admin@marenostrum.com.br","password":"MudeEss@Senha123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
H="Authorization: Bearer $TOKEN"

echo "== Disparando sync locais_votacao_2024 (Brasil inteiro) =="
curl -fsS -X POST "$API/tse/sync?dataset=locais_votacao_2024" -H "$H" | python3 -m json.tool
