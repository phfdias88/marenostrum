#!/usr/bin/env bash
# Bateria de sanidade: valida que as analises fazem SENTIDO (nao so HTTP 200).
API="http://localhost/api/v1"
TOKEN=$(curl -fsS -X POST "$API/auth/login" -H "Content-Type: application/json" \
  -d '{"tenant_slug":"marenostrum-admin","email":"admin@marenostrum.com.br","password":"MudeEss@Senha123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
H="Authorization: Bearer $TOKEN"

muni_id() { # uf, nome -> id
  docker compose -f ~/marenostrum/docker-compose.yml exec -T db psql -U marenostrum -d marenostrum -tA \
    -c "SELECT id FROM tse_municipalities WHERE state='$1' AND name ILIKE '$2' LIMIT 1;"
}

echo "############ 1. ANÁLISE DE ELEIÇÃO (município+cargo) ############"
for spec in "MG|Juiz de Fora|11|Prefeito 2024|2024" \
            "SP|São Paulo|11|Prefeito 2024|2024" \
            "RJ|Rio de Janeiro|13|Vereador 2024|2024" \
            "SP|São Paulo|3|Governador 2022|2022" \
            "MG|Belo Horizonte|3|Governador 2022|2022" \
            "BR_NAT|São Paulo|1|Presidente 2022 (em SP)|2022"; do
  IFS='|' read -r uf nome cargo titulo ano <<< "$spec"
  [ "$uf" = "BR_NAT" ] && uf="SP"
  mid=$(muni_id "$uf" "$nome")
  echo ""
  echo "== $titulo — $nome/$uf =="
  curl -fsS "$API/tse/municipalities/$mid/top-candidates?office_code=$cargo&year=$ano&limit=5" -H "$H" | python3 -c "
import sys,json
d=json.load(sys.stdin)
tot=d['total_votes'] or 1
print(f'  total nominais: {tot:,} | candidatos: {d[\"total_results\"]}')
for i,r in enumerate(d['results'][:5],1):
    c=r['candidate']; pct=r['votes']/tot*100
    print(f'    {i}o {c[\"urn_name\"][:22]:22s} {c[\"party\"][\"abbreviation\"][:6]:6s} {r[\"votes\"]:>10,} ({pct:5.1f}%) {c[\"result_status\"]}')"
done

echo ""
echo "############ 2. ANÁLISE DE CANDIDATO (busca + votos por municipio) ############"
for q in "lula|1" "tarcisio|3" "boulos|11"; do
  IFS='|' read -r nome cargo <<< "$q"
  echo ""
  echo "== busca '$nome' (cargo $cargo) =="
  curl -fsS "$API/tse/candidates?search=$nome&office_code=$cargo&limit=3" -H "$H" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f'  {d[\"total\"]} resultado(s)')
for c in d['items'][:3]:
    print(f'    {c[\"urn_name\"][:25]:25s} {c[\"party\"][\"abbreviation\"]:6s} {c[\"office_name\"]:12s} {c[\"state\"]} {c[\"result_status\"]}')"
done

echo ""
echo "############ 3. VOTOS POR MUNICÍPIO (Lula 2022 — top 5 cidades) ############"
LULA=$(curl -fsS "$API/tse/candidates?search=lula&office_code=1&limit=1" -H "$H" | python3 -c "import sys,json;print(json.load(sys.stdin)['items'][0]['id'])")
curl -fsS "$API/tse/candidates/$LULA/results" -H "$H" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f'  Lula total: {d[\"total_votes\"]:,} em {d[\"municipalities_with_votes\"]:,} municipios')
for r in d['results'][:5]:
    print(f'    {r[\"municipality\"][\"name\"][:25]:25s} {r[\"municipality\"][\"state\"]} {r[\"votes\"]:>10,}')"

echo ""
echo "############ 4. BAIRRO (Margarida JF 2024) ############"
MARG=$(curl -fsS "$API/tse/candidates?search=margarida&state=MG&office_code=11&limit=1" -H "$H" | python3 -c "import sys,json;print(json.load(sys.stdin)['items'][0]['id'])")
JF=$(muni_id MG "Juiz de Fora")
curl -fsS "$API/tse/candidates/$MARG/by-neighborhood?municipality_id=$JF" -H "$H" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f'  total {d[\"total_votes\"]:,} em {d[\"total_neighborhoods\"]} bairros — top 3:')
for it in d['items'][:3]: print(f'    {it[\"neighborhood\"][:25]:25s} {it[\"votes\"]:>7,}')"

echo ""
echo "############ 5. PARTIDOS / ELEIÇÕES / FOTOS ############"
echo -n "  partidos: "; curl -fsS "$API/tse/parties" -H "$H" | python3 -c "import sys,json;print(len(json.load(sys.stdin)))"
echo -n "  eleicoes: "; curl -fsS "$API/tse/elections" -H "$H" | python3 -c "import sys,json;print(len(json.load(sys.stdin)))"
echo -n "  foto Lula: "; curl -s -o /dev/null -w "HTTP %{http_code} %{size_download}B\n" "$API/tse/candidates/$LULA/photo" -H "$H"
echo -n "  foto Margarida: "; curl -s -o /dev/null -w "HTTP %{http_code} %{size_download}B\n" "$API/tse/candidates/$MARG/photo" -H "$H"
