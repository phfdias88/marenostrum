#!/usr/bin/env bash
set -e
API="http://localhost/api/v1"
TOKEN=$(curl -fsS -X POST "$API/auth/login" -H "Content-Type: application/json" \
  -d '{"tenant_slug":"marenostrum-admin","email":"admin@marenostrum.com.br","password":"MudeEss@Senha123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
H="Authorization: Bearer $TOKEN"

echo "== Procurando Margarida (PT/JF) =="
INFO=$(curl -fsS "$API/tse/candidates?state=MG&office_code=11&search=Margarida" -H "$H")
echo "$INFO" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('Total:',d['total'])
for c in d['items']:
    print(f\"  id={c['id']} {c['urn_name']} ({c['party']['abbreviation']})\")"

# Pega o id (primeiro)
CID=$(echo "$INFO" | python3 -c "import sys,json; print(json.load(sys.stdin)['items'][0]['id'])")
echo "CID: $CID"

echo ""
echo "== DB query: sq_candidato + state + election + muni =="
docker compose -f ~/marenostrum/docker-compose.yml exec -T db psql -U marenostrum -d marenostrum -t -c "
SELECT c.sq_candidato || '|' || c.state || '|' || e.tse_code || '|' || e.year
FROM tse_candidates c JOIN tse_elections e ON e.id=c.election_id
WHERE c.id='$CID';
SELECT m.tse_code || '|' || m.name
FROM tse_vote_results vr JOIN tse_municipalities m ON m.id=vr.municipality_id
WHERE vr.candidate_id='$CID' LIMIT 1;
"
