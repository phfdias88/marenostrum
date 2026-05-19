#!/usr/bin/env bash
set -e
JOB_ID="${1:?usage: $0 <job_id>}"
EMAIL="${ADMIN_EMAIL:-admin@marenostrum.com.br}"
PASSWORD="${ADMIN_PASSWORD:-MudeEss@Senha123}"
SLUG="${TENANT_SLUG:-marenostrum-admin}"
API="http://localhost/api/v1"

TOKEN=$(curl -fsS -X POST "$API/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"tenant_slug\":\"$SLUG\",\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -fsS "$API/tse/sync/$JOB_ID" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
