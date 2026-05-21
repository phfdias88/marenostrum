#!/usr/bin/env bash
set -e
API="http://localhost/api/v1"
TOKEN=$(curl -fsS -X POST "$API/auth/login" -H "Content-Type: application/json" \
  -d '{"tenant_slug":"marenostrum-admin","email":"admin@marenostrum.com.br","password":"MudeEss@Senha123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
H="Authorization: Bearer $TOKEN"

echo "== GET /voting-places/by-neighborhood =="
curl -fsS "$API/voting-places/by-neighborhood" -H "$H" | python3 -m json.tool | head -40

echo ""
echo "== HEAD /dashboard/analises/bairros (frontend route) =="
curl -sI http://localhost/dashboard/analises/bairros | head -3
