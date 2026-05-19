#!/usr/bin/env bash
set -e
API="http://localhost/api/v1"
TOKEN=$(curl -fsS -X POST "$API/auth/login" -H "Content-Type: application/json" \
  -d '{"tenant_slug":"marenostrum-admin","email":"admin@marenostrum.com.br","password":"MudeEss@Senha123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
H="Authorization: Bearer $TOKEN"

# Acha a eleicao ordinaria 2024 (round=1, type=Ordinaria) — id que ja vimos: 9a874122
curl -fsS "$API/tse/elections/9a874122-083a-4d04-bbb8-800dfb086b2b/stats" -H "$H" | python3 -m json.tool
