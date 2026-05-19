#!/usr/bin/env bash
set -e
API="http://localhost/api/v1"
TOKEN=$(curl -fsS -X POST "$API/auth/login" -H "Content-Type: application/json" \
  -d '{"tenant_slug":"marenostrum-admin","email":"admin@marenostrum.com.br","password":"MudeEss@Senha123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
H="Authorization: Bearer $TOKEN"

echo "=== 1) result_status nos candidatos (vereadores JF, top 8) ==="
JF=$(curl -fsS "$API/tse/municipalities?state=MG&search=Juiz+de+Fora" -H "$H" | python3 -c "import sys,json;d=json.load(sys.stdin);print([m['id'] for m in d['items'] if m['name'].upper()=='JUIZ DE FORA'][0])")
curl -fsS "$API/tse/municipalities/$JF/top-candidates?office_code=13&limit=8" -H "$H" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f\"Total nominais vereador JF: {d['total_votes']:,} | candidatos: {d['total_results']}\")
for i,r in enumerate(d['results'],1):
    c=r['candidate']
    pct=r['votes']/d['total_votes']*100
    print(f\"  {i}o {c['urn_name']:<25s} {c['party']['abbreviation']:<6s} {r['votes']:>7,} ({pct:.2f}%) -> {c['result_status']}\")"

echo ""
echo "=== 2) Mapa por bairro: Margarida Salomao (prefeito JF) ==="
MARG=185bf3c7-8104-493d-8cdc-88d953c6015f
curl -fsS "$API/tse/candidates/$MARG/by-neighborhood" -H "$H" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f\"Total: {d['total_votes']:,} votos em {d['total_neighborhoods']} bairros\")
for r in d['items'][:8]:
    coord='OK' if r['avg_lat'] else 'sem coord'
    print(f\"  {r['neighborhood']:<30s} {r['votes']:>6,} votos | {r['places_count']} locais | {coord}\")"

echo ""
echo "=== 3) Contagem section_votes (MG) ==="
docker compose -f ~/marenostrum/docker-compose.yml exec -T db psql -U marenostrum -d marenostrum -tA -c "SELECT count(*) FROM tse_section_votes;"
echo "  ^ total section_votes"
docker compose -f ~/marenostrum/docker-compose.yml exec -T db psql -U marenostrum -d marenostrum -tA -c "SELECT count(*) FROM tse_voting_places;"
echo "  ^ total voting_places (Brasil)"
