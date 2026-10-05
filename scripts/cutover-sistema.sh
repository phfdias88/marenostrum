#!/usr/bin/env bash
# =============================================================================
# CORTE PRO SUBDIRETÓRIO /sistema  (rodar NA VPS, em ~/marenostrum)
# =============================================================================
# Pré-requisito EXTERNO: o rewrite já estar ativo no projeto Vercel do site
# principal (marenostrumconsult.com.br) apontando /sistema/* → esta VPS.
# Sem isso, marenostrumconsult.com.br/sistema NÃO chega aqui — mas o corte
# ainda deixa a app funcionando em https://srv1412083.hstgr.cloud/sistema.
#
# Uso:   bash scripts/cutover-sistema.sh          # aplica o corte
#        bash scripts/cutover-sistema.sh --rollback  # volta pra raiz
#
# Idempotente e reversível: faz backup de .env e app.conf antes de mexer.
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."   # raiz do projeto (~/marenostrum)

ROOT_ENV=".env"
BACK_ENV="backend/.env"
NGINX="nginx/conf.d/app.conf"
STAMP="$(date +%Y%m%d-%H%M%S)"

# upsert KEY=VAL num arquivo .env (substitui a linha ou adiciona no fim)
upsert() { # $1=arquivo $2=chave $3=valor
  local f="$1" k="$2" v="$3"
  touch "$f"
  if grep -qE "^${k}=" "$f"; then
    sed -i "s#^${k}=.*#${k}=${v}#" "$f"
  else
    printf '%s=%s\n' "$k" "$v" >> "$f"
  fi
}

if [[ "${1:-}" == "--rollback" ]]; then
  echo "== ROLLBACK pra raiz =="
  upsert "$ROOT_ENV" NEXT_PUBLIC_BASE_PATH ""
  upsert "$ROOT_ENV" NEXT_PUBLIC_API_URL   "https://srv1412083.hstgr.cloud/api"
  upsert "$BACK_ENV" ROOT_PATH             ""
  upsert "$BACK_ENV" PUBLIC_URL_BASE       "https://srv1412083.hstgr.cloud"
  # restaura o app.conf raiz mais recente
  ls -t nginx/conf.d/app.conf.raiz.*.bak >/dev/null 2>&1 && \
    cp "$(ls -t nginx/conf.d/app.conf.raiz.*.bak | head -1)" "$NGINX"
  docker compose exec -T nginx nginx -t
  docker compose build web api
  docker compose up -d web api
  docker compose restart nginx
  docker compose exec -T nginx sh -c 'rm -rf /var/cache/nginx/tse/* /var/cache/nginx/census/*'
  echo "ROLLBACK OK — app na raiz."
  exit 0
fi

echo "== BACKUP =="
cp "$ROOT_ENV" "${ROOT_ENV}.${STAMP}.bak" 2>/dev/null || true
cp "$BACK_ENV" "${BACK_ENV}.${STAMP}.bak"
cp "$NGINX"    "nginx/conf.d/app.conf.raiz.${STAMP}.bak"

echo "== ENV do frontend (build-time) =="
upsert "$ROOT_ENV" NEXT_PUBLIC_BASE_PATH "/sistema"
# RELATIVO: mesma build serve em srv1412083/sistema E marenostrum/sistema,
# same-origin, sem CORS. NÃO hardcode o domínio.
upsert "$ROOT_ENV" NEXT_PUBLIC_API_URL   "/sistema/api"

echo "== ENV do backend =="
upsert "$BACK_ENV" ROOT_PATH       "/sistema"
# QR/rodapé do dossiê apontam pro domínio público final:
upsert "$BACK_ENV" PUBLIC_URL_BASE "https://marenostrumconsult.com.br/sistema"

echo "== nginx pro /sistema =="
cp nginx/conf.d/app.conf.sistema "$NGINX"

echo "== rebuild (basePath é build-time → precisa rebuildar o web) =="
docker compose build web api
docker compose up -d web api

echo "== valida e recarrega nginx =="
docker compose exec -T nginx nginx -t
docker compose restart nginx

echo "== purga cache de borda (paths mudaram) =="
docker compose exec -T nginx sh -c 'rm -rf /var/cache/nginx/tse/* /var/cache/nginx/census/*' || true

echo "== SMOKE (via srv1412083; marenostrum depende do rewrite Vercel) =="
sleep 4
code() { curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$1"; }
echo "  /sistema/login        -> $(code https://srv1412083.hstgr.cloud/sistema/login)   (esperado 200)"
echo "  /sistema/api/health   -> $(code https://srv1412083.hstgr.cloud/sistema/api/health)   (esperado 200)"
echo "  /sistema/api/docs     -> $(code https://srv1412083.hstgr.cloud/sistema/api/docs)   (esperado 200)"
echo "  raiz /dashboard (301) -> $(code https://srv1412083.hstgr.cloud/dashboard)   (esperado 301)"
echo ""
echo "CORTE OK. Se algo falhar: bash scripts/cutover-sistema.sh --rollback"
