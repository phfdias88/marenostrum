#!/usr/bin/env bash
API="http://localhost/api/v1"
TOKEN=$(curl -fsS -X POST "$API/auth/login" -H "Content-Type: application/json" \
  -d '{"tenant_slug":"marenostrum-admin","email":"admin@marenostrum.com.br","password":"MudeEss@Senha123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
H="Authorization: Bearer $TOKEN"

# Pega São Luís via DB direto (capital MA)
SL=$(docker compose -f ~/marenostrum/docker-compose.yml exec -T db psql -U marenostrum -d marenostrum -tA -c "SELECT id FROM tse_municipalities WHERE state='MA' AND name ILIKE 'são luís';")
echo "São Luís id: $SL"

echo "=== Top prefeito São Luís ==="
RESP=$(curl -fsS "$API/tse/municipalities/$SL/top-candidates?office_code=11&limit=3" -H "$H")
echo "$RESP" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('total_votes municipio:', d.get('total_votes'))
for r in d['results'][:3]:
    print('  ', r['candidate']['id'], r['candidate']['urn_name'], r['votes'])
print('CID='+d['results'][0]['candidate']['id'] if d['results'] else 'CID=NONE')
" | tee /tmp/out.txt
CID=$(grep '^CID=' /tmp/out.txt | cut -d= -f2)

echo "=== by-neighborhood (cid=$CID, muni=$SL) ==="
curl -s "$API/tse/candidates/$CID/by-neighborhood?municipality_id=$SL" -H "$H" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('total_votes:', d.get('total_votes'), '| bairros:', d.get('total_neighborhoods'))
for it in d.get('items',[])[:6]: print('  ', it['neighborhood'], it['votes'])"

echo ""
echo "=== section_votes ligados a São Luís? ==="
docker compose -f ~/marenostrum/docker-compose.yml exec -T db psql -U marenostrum -d marenostrum -tA -c "
SELECT count(*) FROM tse_section_votes sv JOIN tse_voting_places vp ON vp.id=sv.voting_place_id WHERE vp.municipality_id='$SL';"
