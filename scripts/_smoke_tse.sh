#!/usr/bin/env bash
set -e
EMAIL="${ADMIN_EMAIL:-admin@marenostrum.com.br}"
PASSWORD="${ADMIN_PASSWORD:-MudeEss@Senha123}"
SLUG="${TENANT_SLUG:-marenostrum-admin}"
API="http://localhost/api/v1"

TOKEN=$(curl -fsS -X POST "$API/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"tenant_slug\":\"$SLUG\",\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

H="Authorization: Bearer $TOKEN"

echo "===== GET /tse/parties (top 5) ====="
curl -fsS "$API/tse/parties" -H "$H" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f'Total: {len(d)} partidos')
for p in sorted(d, key=lambda x: x['number'])[:8]:
    print(f\"  {p['number']:>3} {p['abbreviation']:<8s} {p['name']}\")"

echo ""
echo "===== GET /tse/elections ====="
curl -fsS "$API/tse/elections" -H "$H" | python3 -m json.tool

echo ""
echo "===== GET /tse/candidates?state=MG&office_code=11&search=Lula (prefeitos MG 'Lula') ====="
curl -fsS "$API/tse/candidates?state=MG&office_code=11&search=Lula&limit=5" -H "$H" \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f\"Total matches: {d['total']}, returned: {len(d['items'])}\")
for c in d['items']:
    print(f\"  {c['urn_name']:<30s} | {c['party']['abbreviation']:<6s} | {c['situation']}\")"

echo ""
echo "===== GET /tse/candidates?state=MG&office_code=11&limit=3 (prefeitos MG top 3) ====="
RES=$(curl -fsS "$API/tse/candidates?state=MG&office_code=11&limit=3" -H "$H")
echo "$RES" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f\"Total prefeitos MG 2024: {d['total']}\")
for c in d['items']:
    print(f\"  [{c['id']}] {c['urn_name']:<25s} | {c['party']['abbreviation']:<6s} | {c['situation']}\")"
FIRST_ID=$(echo "$RES" | python3 -c "import sys,json; print(json.load(sys.stdin)['items'][0]['id'])")

echo ""
echo "===== GET /tse/candidates/$FIRST_ID/results (votos por municipio do primeiro) ====="
curl -fsS "$API/tse/candidates/$FIRST_ID/results" -H "$H" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f\"Candidato: {d['candidate']['urn_name']} ({d['candidate']['party']['abbreviation']})\")
print(f\"Total votos: {d['total_votes']:,}\")
print(f\"Municipios com voto: {d['municipalities_with_votes']}\")
print('Top 5 municipios:')
for r in d['results'][:5]:
    print(f\"  {r['municipality']['name']:<25s} {r['municipality']['state']} {r['votes']:>8,} votos\")"
