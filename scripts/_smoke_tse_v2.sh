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

echo "===== GET /tse/municipalities?state=MG&search=Juiz ====="
curl -fsS "$API/tse/municipalities?state=MG&search=Juiz" -H "$H" \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f'Total: {d[\"total\"]}')
for m in d['items']:
    print(f\"  [{m['id'][:8]}] {m['name']:<30s} {m['state']} (TSE {m['tse_code']})\")"

echo ""
echo "===== Procura Juiz de Fora especificamente ====="
JFID=$(curl -fsS "$API/tse/municipalities?state=MG&search=Juiz+de+Fora" -H "$H" \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
target=[m for m in d['items'] if m['name'].upper()=='JUIZ DE FORA']
if target: print(target[0]['id'])
else: print('NOTFOUND')")
echo "JF id: $JFID"

echo ""
echo "===== GET /tse/municipalities/$JFID/top-candidates?office_code=11 (Prefeito de JF) ====="
curl -fsS "$API/tse/municipalities/$JFID/top-candidates?office_code=11&limit=10" -H "$H" \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f\"Municipio: {d['municipality']['name']} / {d['municipality']['state']}\")
print(f\"Top {d['total_results']} candidatos:\")
for i,r in enumerate(d['results'],1):
    print(f\"  {i:>2}. {r['candidate']['urn_name']:<25s} ({r['candidate']['party']['abbreviation']:<6s}) {r['votes']:>8,} votos\")"

echo ""
echo "===== GET /tse/elections/{id}/stats (Eleicoes Municipais 2024) ====="
ELID=$(curl -fsS "$API/tse/elections" -H "$H" \
  | python3 -c "
import sys,json
arr=json.load(sys.stdin)
ord=[e for e in arr if e.get('type_name','').lower().startswith('elei') and 'ordin' in e['type_name'].lower() and e['round']==1]
print(ord[0]['id'] if ord else 'NOTFOUND')")
echo "Eleicao ordinaria 2024 id: $ELID"

curl -fsS "$API/tse/elections/$ELID/stats" -H "$H" | python3 -m json.tool
