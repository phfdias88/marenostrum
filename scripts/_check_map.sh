#!/usr/bin/env bash
set -e
API="http://localhost/api/v1"
TOKEN=$(curl -fsS -X POST "$API/auth/login" -H "Content-Type: application/json" \
  -d '{"tenant_slug":"marenostrum-admin","email":"admin@marenostrum.com.br","password":"MudeEss@Senha123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
H="Authorization: Bearer $TOKEN"

# Margarida
echo "== Resultados Margarida (deve ter lat/lng nos munis) =="
curl -fsS "$API/tse/candidates/185bf3c7-8104-493d-8cdc-88d953c6015f/results" -H "$H" \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f\"Total votos: {d['total_votes']:,}\")
print(f\"Municipios: {d['municipalities_with_votes']}\")
for r in d['results'][:3]:
    m=r['municipality']
    print(f\"  {m['name']}/{m['state']}: {r['votes']:,} votos | lat={m.get('latitude')} lng={m.get('longitude')}\")"

echo ""
echo "== Pega 1 candidato com votos em varias cidades (vereador SP top) =="
TOP=$(curl -fsS "$API/tse/candidates?state=SP&office_code=13&limit=5" -H "$H" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['items'][0]['id'])")
echo "ID: $TOP"
curl -fsS "$API/tse/candidates/$TOP/results" -H "$H" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f\"Candidato: {d['candidate']['urn_name']} ({d['candidate']['party']['abbreviation']})\")
print(f\"Total: {d['total_votes']:,} em {d['municipalities_with_votes']} munis\")
with_coords = sum(1 for r in d['results'] if r['municipality'].get('latitude'))
print(f\"Com coords: {with_coords}/{len(d['results'])}\")"
