#!/usr/bin/env bash
API="http://localhost/api/v1"
TOKEN=$(curl -fsS -X POST "$API/auth/login" -H "Content-Type: application/json" \
  -d '{"tenant_slug":"marenostrum-admin","email":"admin@marenostrum.com.br","password":"MudeEss@Senha123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
H="Authorization: Bearer $TOKEN"

echo "=== Busca presidente 2022 (Lula/Bolsonaro) ==="
curl -fsS "$API/tse/candidates?office_code=1&year=2022&limit=15" -H "$H" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f\"Total presidentes 2022: {d['total']}\")
for c in d['items']:
    print(f\"  {c['number']:>2} {c['urn_name']:<25s} {c['party']['abbreviation']:<6s} {c['result_status']}\")"

echo ""
echo "=== Governador SP 2022 ==="
curl -fsS "$API/tse/candidates?state=SP&office_code=3&year=2022&limit=8" -H "$H" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f\"Total gov SP 2022: {d['total']}\")
for c in d['items'][:6]:
    print(f\"  {c['number']:>2} {c['urn_name']:<25s} {c['party']['abbreviation']:<6s} {c['result_status']}\")"

echo ""
echo "=== Foto de um governador 2022 (UF real) — pega o 1o ==="
GID=$(curl -fsS "$API/tse/candidates?state=SP&office_code=3&year=2022&limit=1" -H "$H" | python3 -c "import sys,json;print(json.load(sys.stdin)['items'][0]['id'])")
echo "id: $GID"
curl -s "$API/tse/candidates/$GID/photo" -H "$H" -o /tmp/gov.jpg -w "  foto: HTTP %{http_code}, %{size_download} bytes, %{time_total}s\n"

echo ""
echo "=== Resultado presidente em Sao Paulo (cidade) 2022 ==="
SPID=$(curl -fsS "$API/tse/municipalities?state=SP&search=São+Paulo" -H "$H" | python3 -c "import sys,json;d=json.load(sys.stdin);print([m['id'] for m in d['items'] if m['name'].upper()=='SÃO PAULO'][0])")
curl -fsS "$API/tse/municipalities/$SPID/top-candidates?office_code=1&year=2022&limit=15" -H "$H" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f\"{d['municipality']['name']}/{d['municipality']['state']} — Presidente 2022 — total {d['total_votes']:,} votos\")
for i,r in enumerate(d['results'],1):
    c=r['candidate']
    pct=r['votes']/max(d['total_votes'],1)*100
    print(f\"  {i}o {c['urn_name']:<22s} {c['party']['abbreviation']:<6s} {r['votes']:>10,} ({pct:.1f}%)\")"
