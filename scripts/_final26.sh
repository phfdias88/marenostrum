#!/usr/bin/env bash
API="http://localhost/api/v1"
TOKEN=$(curl -fsS -X POST "$API/auth/login" -H "Content-Type: application/json" \
  -d '{"tenant_slug":"marenostrum-admin","email":"admin@marenostrum.com.br","password":"MudeEss@Senha123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
H="Authorization: Bearer $TOKEN"
mid() { docker compose -f ~/marenostrum/docker-compose.yml exec -T db psql -U marenostrum -d marenostrum -tA -c "SELECT id FROM tse_municipalities WHERE state='$1' AND name ILIKE '$2' LIMIT 1;"; }

echo "=== Foto presidente (Lula/Bolsonaro) ==="
for nm in lula bolsonaro; do
  id=$(curl -fsS "$API/tse/candidates?search=$nm&office_code=1&limit=1" -H "$H" | python3 -c "import sys,json;print(json.load(sys.stdin)['items'][0]['id'])")
  curl -s -o /dev/null -w "  $nm: HTTP %{http_code} %{size_download}B %{time_total}s\n" "$API/tse/candidates/$id/photo" -H "$H"
done

echo ""
echo "=== Bairro BA (Salvador prefeito 2024) ==="
SSA=$(mid BA "salvador")
CID=$(curl -fsS "$API/tse/municipalities/$SSA/top-candidates?office_code=11&limit=1" -H "$H" | python3 -c "import sys,json;print(json.load(sys.stdin)['results'][0]['candidate']['id'])")
curl -fsS "$API/tse/candidates/$CID/by-neighborhood?municipality_id=$SSA" -H "$H" | python3 -c "
import sys,json;d=json.load(sys.stdin)
print(f'  {d[\"total_votes\"]:,} votos em {d[\"total_neighborhoods\"]} bairros — top 3:')
for it in d['items'][:3]: print(f'    {it[\"neighborhood\"][:28]:28s} {it[\"votes\"]:>7,}')"

echo ""
echo "=== Bairro SP (São Paulo prefeito 2024) ==="
SP=$(mid SP "são paulo")
CID2=$(curl -fsS "$API/tse/municipalities/$SP/top-candidates?office_code=11&limit=1" -H "$H" | python3 -c "import sys,json;print(json.load(sys.stdin)['results'][0]['candidate']['id'])")
curl -fsS "$API/tse/candidates/$CID2/by-neighborhood?municipality_id=$SP" -H "$H" | python3 -c "
import sys,json;d=json.load(sys.stdin)
print(f'  {d[\"total_votes\"]:,} votos em {d[\"total_neighborhoods\"]} bairros — top 3:')
for it in d['items'][:3]: print(f'    {it[\"neighborhood\"][:28]:28s} {it[\"votes\"]:>7,}')"

echo ""
echo "=== Cobertura final: UFs com dados de bairro ==="
docker compose -f ~/marenostrum/docker-compose.yml exec -T db psql -U marenostrum -d marenostrum -tA -c "
SELECT count(DISTINCT m.state) FROM tse_section_votes sv JOIN tse_voting_places vp ON vp.id=sv.voting_place_id JOIN tse_municipalities m ON m.id=vp.municipality_id;"
echo "  ^ total UFs com bairro (de 27; DF nao tem eleicao municipal)"
