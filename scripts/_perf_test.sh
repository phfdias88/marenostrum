#!/usr/bin/env bash
# Testa endpoints + mede tempo de resposta (server-side, sem latencia de rede).
API="http://localhost/api/v1"
TOKEN=$(curl -fsS -X POST "$API/auth/login" -H "Content-Type: application/json" \
  -d '{"tenant_slug":"marenostrum-admin","email":"admin@marenostrum.com.br","password":"MudeEss@Senha123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
H="Authorization: Bearer $TOKEN"

timeit() {
  local name="$1" url="$2"
  local out code t
  out=$(curl -s -o /dev/null -w "%{http_code} %{time_total}" "$API$url" -H "$H")
  code=$(echo "$out" | cut -d' ' -f1)
  t=$(echo "$out" | cut -d' ' -f2)
  printf "  %-45s [%s] %ss\n" "$name" "$code" "$t"
}

JF=$(curl -s "$API/tse/municipalities?state=MG&search=Juiz+de+Fora" -H "$H" | python3 -c "import sys,json;d=json.load(sys.stdin);print([m['id'] for m in d['items'] if m['name'].upper()=='JUIZ DE FORA'][0])")
MARG=$(curl -s "$API/tse/candidates?state=MG&office_code=11&search=Margarida&limit=1" -H "$H" | python3 -c "import sys,json;print(json.load(sys.stdin)['items'][0]['id'])")

echo "===== TEMPOS DE RESPOSTA ====="
timeit "parties" "/tse/parties"
timeit "elections" "/tse/elections"
timeit "candidates MG prefeito (lista)" "/tse/candidates?state=MG&office_code=11&limit=20"
timeit "candidates busca 'silva' (ILIKE)" "/tse/candidates?search=silva&limit=20"
timeit "candidates busca 'maria' SP vereador" "/tse/candidates?state=SP&office_code=13&search=maria&limit=20"
timeit "candidates 2022 governador" "/tse/candidates?office_code=3&year=2022&limit=20"
timeit "candidates 2022 presidente" "/tse/candidates?office_code=1&year=2022&limit=20"
timeit "muni top-candidates JF prefeito" "/tse/municipalities/$JF/top-candidates?office_code=11&limit=50"
timeit "muni top-candidates JF vereador" "/tse/municipalities/$JF/top-candidates?office_code=13&limit=100"
timeit "candidate results (Margarida)" "/tse/candidates/$MARG/results"
timeit "candidate by-neighborhood (Margarida)" "/tse/candidates/$MARG/by-neighborhood?municipality_id=$JF"
timeit "municipalities busca 'sao'" "/tse/municipalities?search=sao&limit=30"

echo ""
echo "===== Dados 2022 (sanity) ====="
curl -s "$API/tse/candidates?office_code=1&year=2022&limit=5" -H "$H" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f'Presidente 2022: {d[\"total\"]} candidatos')
for c in d['items'][:5]: print(f'  {c[\"urn_name\"]} ({c[\"party\"][\"abbreviation\"]}) -> {c[\"result_status\"]}')"

echo ""
echo "===== Indices em tse_candidates ====="
docker compose -f ~/marenostrum/docker-compose.yml exec -T db psql -U marenostrum -d marenostrum -tA -c "
SELECT indexname FROM pg_indexes WHERE tablename='tse_candidates' ORDER BY indexname;"
echo ""
echo "===== EXPLAIN da busca ILIKE (gargalo provavel) ====="
docker compose -f ~/marenostrum/docker-compose.yml exec -T db psql -U marenostrum -d marenostrum -c "
EXPLAIN ANALYZE SELECT id FROM tse_candidates WHERE urn_name ILIKE '%silva%' OR name ILIKE '%silva%' ORDER BY urn_name LIMIT 20;" 2>&1 | head -20
