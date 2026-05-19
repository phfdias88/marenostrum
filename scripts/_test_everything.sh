#!/usr/bin/env bash
# Testa TODOS os endpoints TSE end-to-end e reporta OK/FALHA.
API="http://localhost/api/v1"
TOKEN=$(curl -fsS -X POST "$API/auth/login" -H "Content-Type: application/json" \
  -d '{"tenant_slug":"marenostrum-admin","email":"admin@marenostrum.com.br","password":"MudeEss@Senha123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
H="Authorization: Bearer $TOKEN"

pass=0; fail=0
check() {
  local name="$1" url="$2" jqcheck="$3"
  local body code
  body=$(curl -s -w $'\n%{http_code}' "$API$url" -H "$H")
  code=$(echo "$body" | tail -1)
  body=$(echo "$body" | head -n -1)
  if [ "$code" != "200" ]; then
    echo "  FALHA [$code] $name ($url)"
    fail=$((fail+1)); return
  fi
  local res
  res=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print($jqcheck)" 2>/dev/null)
  if [ -z "$res" ] || [ "$res" = "ERR" ]; then
    echo "  FALHA [parse] $name"
    fail=$((fail+1)); return
  fi
  echo "  OK   $name -> $res"
  pass=$((pass+1))
}

echo "===== TESTE COMPLETO DOS ENDPOINTS TSE ====="
check "parties"          "/tse/parties"                              "f\"{len(d)} partidos\""
check "elections"        "/tse/elections"                            "f\"{len(d)} eleicoes\""
check "candidates list"  "/tse/candidates?state=MG&office_code=11&limit=5"  "f\"{d['total']} prefeitos MG\""
check "candidates search" "/tse/candidates?search=margarida&limit=3"  "f\"{d['total']} matches 'margarida'\""
check "municipalities"   "/tse/municipalities?state=MG&search=juiz"  "f\"{d['total']} munis 'juiz' MG\""

# IDs dinamicos
JF=$(curl -s "$API/tse/municipalities?state=MG&search=Juiz+de+Fora" -H "$H" | python3 -c "import sys,json;d=json.load(sys.stdin);print([m['id'] for m in d['items'] if m['name'].upper()=='JUIZ DE FORA'][0])")
MARG=$(curl -s "$API/tse/candidates?state=MG&office_code=11&search=Margarida&limit=1" -H "$H" | python3 -c "import sys,json;print(json.load(sys.stdin)['items'][0]['id'])")
ELID=$(curl -s "$API/tse/elections" -H "$H" | python3 -c "import sys,json;a=json.load(sys.stdin);print([e['id'] for e in a if 'ordin' in (e.get('type_name') or '').lower() and e['round']==1][0])")

check "muni top-cand"    "/tse/municipalities/$JF/top-candidates?office_code=11&limit=5" "f\"top: {d['results'][0]['candidate']['urn_name']} ({d['results'][0]['votes']:,}) | total {d['total_votes']:,}\""
check "candidate results" "/tse/candidates/$MARG/results"           "f\"{d['total_votes']:,} votos / {d['municipalities_with_votes']} munis\""
check "candidate bairros" "/tse/candidates/$MARG/by-neighborhood?municipality_id=$JF" "f\"{d['total_votes']:,} votos / {d['total_neighborhoods']} bairros\""
check "election stats"   "/tse/elections/$ELID/stats"               "f\"{d['candidates_count']:,} cand / {d['total_votes']:,} votos\""
check "candidate photo"  "/tse/candidates/$MARG/photo"              "'(foto — endpoint nao-JSON, ver abaixo)'" 2>/dev/null

# Foto e' binaria, testa separado
PCODE=$(curl -s -o /dev/null -w "%{http_code}" "$API/tse/candidates/$MARG/photo" -H "$H")
PSIZE=$(curl -s "$API/tse/candidates/$MARG/photo" -H "$H" | wc -c)
echo "  FOTO [$PCODE] $PSIZE bytes"

echo ""
echo "===== Contagens no DB ====="
docker compose -f ~/marenostrum/docker-compose.yml exec -T db psql -U marenostrum -d marenostrum -tA -c "
SELECT 'candidatos: '||count(*) FROM tse_candidates
UNION ALL SELECT 'municipios: '||count(*) FROM tse_municipalities
UNION ALL SELECT 'municipios c/ coord: '||count(*) FROM tse_municipalities WHERE latitude IS NOT NULL
UNION ALL SELECT 'partidos: '||count(*) FROM tse_parties
UNION ALL SELECT 'vote_results: '||count(*) FROM tse_vote_results
UNION ALL SELECT 'voting_places: '||count(*) FROM tse_voting_places
UNION ALL SELECT 'section_votes: '||count(*) FROM tse_section_votes
UNION ALL SELECT 'candidatos eleitos: '||count(*) FROM tse_candidates WHERE result_status LIKE 'ELEITO%';
"

echo ""
echo "===== UFs com dados de secao (bairro disponivel) ====="
docker compose -f ~/marenostrum/docker-compose.yml exec -T db psql -U marenostrum -d marenostrum -tA -c "
SELECT m.state, count(DISTINCT sv.id) AS votos_secao
FROM tse_section_votes sv
JOIN tse_voting_places vp ON vp.id = sv.voting_place_id
JOIN tse_municipalities m ON m.id = vp.municipality_id
GROUP BY m.state ORDER BY m.state;
"

echo ""
echo "===== RESULTADO: $pass OK, $fail FALHAS ====="
