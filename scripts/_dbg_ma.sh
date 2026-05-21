#!/usr/bin/env bash
API="http://localhost/api/v1"
TOKEN=$(curl -fsS -X POST "$API/auth/login" -H "Content-Type: application/json" \
  -d '{"tenant_slug":"marenostrum-admin","email":"admin@marenostrum.com.br","password":"MudeEss@Senha123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
H="Authorization: Bearer $TOKEN"

echo "=== Sao Luis MA ==="
SL=$(curl -fsS "$API/tse/municipalities?state=MA&search=Luis&limit=20" -H "$H" | python3 -c "
import sys,json
d=json.load(sys.stdin)
for m in d['items']:
    if 'LU' in m['name'].upper() and 'S' in m['name'].upper():
        print(m['id']); break")
echo "Sao Luis id: $SL"

echo "=== Top prefeito Sao Luis ==="
curl -fsS "$API/tse/municipalities/$SL/top-candidates?office_code=11&limit=3" -H "$H" | python3 -c "
import sys,json
d=json.load(sys.stdin)
for r in d['results'][:3]:
    print(' ', r['candidate']['id'], r['candidate']['urn_name'], r['votes'])
import json as j
cid=d['results'][0]['candidate']['id']
open('/tmp/cid.txt','w').write(cid)"

CID=$(cat /tmp/cid.txt)
echo "=== by-neighborhood do top (cid=$CID) ==="
curl -s "$API/tse/candidates/$CID/by-neighborhood?municipality_id=$SL" -H "$H" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('total_votes:', d['total_votes'], '| bairros:', d['total_neighborhoods'])
for it in d['items'][:5]: print('  ', it['neighborhood'], it['votes'])"

echo ""
echo "=== DB: voting_places + section_votes em MA ==="
docker compose -f ~/marenostrum/docker-compose.yml exec -T db psql -U marenostrum -d marenostrum -tA -c "
SELECT 'voting_places MA: '||count(*) FROM tse_voting_places vp JOIN tse_municipalities m ON m.id=vp.municipality_id WHERE m.state='MA'
UNION ALL
SELECT 'voting_places MA c/ bairro: '||count(*) FROM tse_voting_places vp JOIN tse_municipalities m ON m.id=vp.municipality_id WHERE m.state='MA' AND vp.neighborhood IS NOT NULL;"
