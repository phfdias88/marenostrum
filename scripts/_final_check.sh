#!/usr/bin/env bash
API="http://localhost/api/v1"
TOKEN=$(curl -fsS -X POST "$API/auth/login" -H "Content-Type: application/json" \
  -d '{"tenant_slug":"marenostrum-admin","email":"admin@marenostrum.com.br","password":"MudeEss@Senha123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
H="Authorization: Bearer $TOKEN"

echo "=== Fotos: 10 governadores SP 2022 (testa .jpg/.jpeg) ==="
IDS=$(curl -fsS "$API/tse/candidates?state=SP&office_code=3&year=2022&limit=10" -H "$H" | python3 -c "import sys,json;print(' '.join(c['id'] for c in json.load(sys.stdin)['items']))")
ok=0; nf=0
for id in $IDS; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "$API/tse/candidates/$id/photo" -H "$H")
  if [ "$code" = "200" ]; then ok=$((ok+1)); else nf=$((nf+1)); fi
done
echo "  fotos OK: $ok | sem foto (404): $nf de 10"

echo ""
echo "=== Presidente em SP capital 2022 ==="
SPID=$(curl -fsS "$API/tse/municipalities?state=SP&search=Paulo&limit=50" -H "$H" | python3 -c "import sys,json;d=json.load(sys.stdin);print([m['id'] for m in d['items'] if m['name'].upper()=='SAO PAULO' or m['name'].upper()=='SÃO PAULO'][0])")
curl -fsS "$API/tse/municipalities/$SPID/top-candidates?office_code=1&year=2022&limit=12" -H "$H" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f\"{d['municipality']['name']} — Presidente 2022 — {d['total_votes']:,} votos nominais\")
for i,r in enumerate(d['results'],1):
    c=r['candidate']; pct=r['votes']/max(d['total_votes'],1)*100
    print(f\"  {i}o {c['urn_name']:<20s} {c['party']['abbreviation']:<6s} {r['votes']:>9,} ({pct:.1f}%)\")"

echo ""
echo "=== Sanidade: timings finais ==="
for u in "candidates?search=bolsonaro&limit=20" "candidates?search=lula&limit=20" "candidates?state=SP&office_code=7&year=2022&limit=20"; do
  t=$(curl -s -o /dev/null -w '%{time_total}' "$API/tse/$u" -H "$H")
  printf "  %ss  %s\n" "$t" "$u"
done
