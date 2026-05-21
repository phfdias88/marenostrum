#!/usr/bin/env bash
API="http://localhost/api/v1"
TOKEN=$(curl -fsS -X POST "$API/auth/login" -H "Content-Type: application/json" \
  -d '{"tenant_slug":"marenostrum-admin","email":"admin@marenostrum.com.br","password":"MudeEss@Senha123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
H="Authorization: Bearer $TOKEN"

echo "=== Contagens ==="
docker compose -f ~/marenostrum/docker-compose.yml exec -T db psql -U marenostrum -d marenostrum -tA -c "
SELECT 'candidatos: '||count(*) FROM tse_candidates
UNION ALL SELECT '  2024: '||count(*) FROM tse_candidates c JOIN tse_elections e ON e.id=c.election_id WHERE e.year=2024
UNION ALL SELECT '  2022: '||count(*) FROM tse_candidates c JOIN tse_elections e ON e.id=c.election_id WHERE e.year=2022
UNION ALL SELECT 'vote_results: '||count(*) FROM tse_vote_results
UNION ALL SELECT 'partidos: '||count(*) FROM tse_parties
UNION ALL SELECT 'eleicoes: '||count(*) FROM tse_elections;"

echo ""
echo "=== Cargos por ano ==="
docker compose -f ~/marenostrum/docker-compose.yml exec -T db psql -U marenostrum -d marenostrum -tA -c "
SELECT e.year, c.office_name, count(*) FROM tse_candidates c JOIN tse_elections e ON e.id=c.election_id
GROUP BY e.year, c.office_code, c.office_name ORDER BY e.year DESC, c.office_code;"

echo ""
echo "=== TIMING das consultas (curl total time) ==="
timeit() { local n="$1" u="$2"; local t=$(curl -s -o /dev/null -w '%{time_total}' "$API$u" -H "$H"); printf '  %6ss  %s\n' "$t" "$n"; }
timeit "busca candidato 'bolsonaro'"   "/tse/candidates?search=bolsonaro&limit=20"
timeit "busca candidato 'silva'"        "/tse/candidates?search=silva&limit=20"
timeit "candidatos MG vereador"         "/tse/candidates?state=MG&office_code=13&limit=20"
timeit "candidatos presidente 2022"     "/tse/candidates?office_code=1&year=2022&limit=20"
timeit "busca municipio 'sao paulo'"    "/tse/municipalities?search=sao+paulo&limit=20"
timeit "parties"                        "/tse/parties"
