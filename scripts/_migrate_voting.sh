#!/usr/bin/env bash
# Migra os 2027 locais de votacao que foram (erroneamente) importados como
# contacts tipo Outro pra o novo modelo VotingPlace.
#
# Etapas:
# 1. Login → JWT
# 2. SQL: limpa contacts com type=other E notes LIKE '%Adriana Kutwak%'
# 3. POST /voting-places/import com o CSV original
# 4. Confirma via /heatmap
set -euo pipefail

BASE="http://localhost"
CSV="/tmp/votos_adriana_kutwak.csv"

if [[ ! -f "$CSV" ]]; then
    echo "ERRO: nao achei $CSV — faz scp do CSV original primeiro"
    exit 1
fi

echo "=== 1) Login → token ==="
TOKEN=$(curl -s -X POST $BASE/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"tenant_slug":"marenostrum-admin","email":"admin@marenostrum.com.br","password":"MudeEss@Senha123"}' \
    | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
echo "Token: ${TOKEN:0:40}..."

echo
echo "=== 2) Limpa contacts erroneamente importados (type=other, notes Adriana) ==="
DELETED=$(docker compose -f /home/deploy/marenostrum/docker-compose.yml exec -T db \
    psql -U marenostrum -d marenostrum -t -c \
    "DELETE FROM contacts WHERE type='other' AND notes LIKE '%Adriana Kutwak%' RETURNING id;" \
    | wc -l)
echo "Linhas afetadas: $DELETED"

echo
echo "=== 3) Importa pelo endpoint CORRETO /voting-places/import ==="
RESPONSE=$(curl -s -X POST "$BASE/api/v1/voting-places/import" \
    -H "Authorization: Bearer $TOKEN" \
    -F "file=@$CSV" \
    -F "election_year=2024" \
    -F "replace_existing=true")
echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"

echo
echo "=== 4) Confirma via /heatmap ==="
curl -s "$BASE/api/v1/voting-places/heatmap" \
    -H "Authorization: Bearer $TOKEN" \
    | python3 -c 'import sys,json; d=json.load(sys.stdin); print(f"Pontos no heatmap: {len(d[\"points\"])}"); print(f"Total locais: {d[\"total_places\"]}"); print(f"Total votos: {d[\"total_votes\"]}"); print(f"Max votos em 1 local: {d[\"max_votes\"]}")'

echo
echo "OK. Abra: http://srv1412083.hstgr.cloud/dashboard/map → toggle 'Heatmap'"
