#!/usr/bin/env bash
# Migra de IP cru pra hostname srv1412083.hstgr.cloud
# (Chrome bloqueia HTTP em IP publico cru por reputacao Safe Browsing)
set -euo pipefail

cd /home/deploy/marenostrum

HOST="srv1412083.hstgr.cloud"

echo "=== 1) backup .envs ==="
cp -n .env .env.bak.$(date +%s) 2>/dev/null || true
cp -n backend/.env backend/.env.bak.$(date +%s) 2>/dev/null || true

echo "=== 2) atualiza .env raiz (NEXT_PUBLIC_API_URL) ==="
sed -i "s|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=http://${HOST}/api|" .env
grep NEXT_PUBLIC_API_URL .env

echo "=== 3) atualiza backend/.env (CORS) ==="
# Inclui IP + hostname (mantem compat com curl direto pelo IP)
sed -i "s|^CORS_ORIGINS=.*|CORS_ORIGINS=[\"http://${HOST}\",\"http://72.60.248.41\",\"http://localhost:3000\"]|" backend/.env
grep CORS_ORIGINS backend/.env

echo "=== 4) rebuild web (Next inlina vars em build time) ==="
docker compose up -d --build web 2>&1 | tail -8

echo "=== 5) restart api (pra pegar novo CORS) ==="
docker compose restart api 2>&1 | tail -3

echo "=== 6) aguarda health ==="
for i in {1..20}; do
    if curl -s -o /dev/null -w '%{http_code}' http://localhost/api/health 2>/dev/null | grep -q 200; then
        echo "OK API responde"
        break
    fi
    sleep 2
done

echo
echo "PRONTO. Use no browser: http://${HOST}/login"
