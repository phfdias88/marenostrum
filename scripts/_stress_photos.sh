#!/usr/bin/env bash
# Stress test: 8 fotos em paralelo no mesmo UF (MG) — forca race condition
set -e
cd ~/marenostrum

echo "== Limpa cache MG pra forcar fetch real =="
docker compose exec -T api rm -rf /var/marenostrum/tse_photos/MG 2>/dev/null
docker compose exec -T api ls /var/marenostrum/tse_photos/ 2>/dev/null || echo "  (vazio)"

# Pega 8 IDs de candidatos MG/Prefeito
API="http://localhost/api/v1"
TOKEN=$(curl -fsS -X POST "$API/auth/login" -H "Content-Type: application/json" \
  -d '{"tenant_slug":"marenostrum-admin","email":"admin@marenostrum.com.br","password":"MudeEss@Senha123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

IDS=$(curl -fsS "$API/tse/candidates?state=MG&office_code=11&limit=8" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(' '.join(c['id'] for c in d['items']))")
echo "8 ids: $IDS"

echo ""
echo "== Dispara 8 requests em paralelo =="
for id in $IDS; do
  curl -s "http://localhost/api/v1/tse/candidates/$id/photo" \
    -o /tmp/p_$id.jpg \
    -w "%{http_code} size=%{size_download} time=%{time_total}s $id\n" &
done
wait

echo ""
echo "== Conta sucessos =="
ls /tmp/p_*.jpg | while read f; do
  size=$(stat -c%s "$f")
  if [ "$size" -gt 1000 ]; then
    echo "  OK $(basename $f .jpg | sed 's/p_//') ($size bytes)"
  else
    echo "  FAIL $(basename $f .jpg | sed 's/p_//') ($size bytes)"
  fi
done | sort | uniq -c -w 6
rm -f /tmp/p_*.jpg
