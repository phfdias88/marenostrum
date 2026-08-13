#!/usr/bin/env bash
# =============================================================================
# Coloca SITE + SISTEMA no domínio de vocês, servidos pela NOSSA VPS.
#
# POR QUÊ: hoje o domínio depende da Vercel (site) que por sua vez redireciona
# o /sistema pra cá. Quando o DNS saiu da Vercel, tudo caiu. Servindo os dois
# da mesma máquina, o domínio passa a ter UM destino só — menos peças, menos
# chance de cair de novo.
#
# O site é 100% estático (Vite) e só conversa com a nossa API (/sistema/api/*)
# e com serviços externos (Firebase, formulário) — nada dele exigia a Vercel.
#
# PRÉ-REQUISITO (painel do domínio, hPanel Hostinger):
#   Tipo A   @      ->  72.60.248.41
#   Tipo A   www    ->  72.60.248.41
#   (removendo os A antigos que apontam pro WordPress)
#
# USO (na VPS, em ~/marenostrum):
#   bash scripts/setup-dominio-proprio.sh marenostrumconsult.com.br seu@email.com
# =============================================================================
set -euo pipefail

DOMAIN="${1:?informe o domínio, ex: marenostrumconsult.com.br}"
EMAIL="${2:?informe um e-mail para avisos do Let's Encrypt}"
CONF="nginx/conf.d/site-dominio.conf"
SITE_DIR="/home/deploy/marenostrum/site-dist"

cd "$(dirname "$0")/.."

echo "==> 1/5 conferindo DNS"
IP_DNS="$(getent hosts "$DOMAIN" | awk '{print $1}' | head -1 || echo '')"
if [ "$IP_DNS" != "72.60.248.41" ]; then
  echo "ERRO: $DOMAIN aponta para '${IP_DNS:-nada}', esperado 72.60.248.41." >&2
  echo "      Ajuste o registro A no painel e aguarde a propagação." >&2
  exit 1
fi
echo "    OK: $DOMAIN -> $IP_DNS"

echo "==> 2/5 conferindo se o site estático foi enviado"
if [ ! -f "$SITE_DIR/index.html" ]; then
  echo "ERRO: $SITE_DIR/index.html não existe." >&2
  echo "      Envie o build antes (feito pelo agente a partir de marenostrum-platform/dist)." >&2
  exit 1
fi
echo "    OK: $(find "$SITE_DIR" -type f | wc -l) arquivos"

echo "==> 3/5 emitindo certificado (domínio + www)"
docker compose stop nginx >/dev/null 2>&1 || true
docker run --rm -p 80:80 \
  -v /etc/letsencrypt:/etc/letsencrypt \
  -v /var/lib/letsencrypt:/var/lib/letsencrypt \
  certbot/certbot certonly --standalone \
  -d "$DOMAIN" -d "www.$DOMAIN" \
  --agree-tos -m "$EMAIL" --no-eff-email --non-interactive

echo "==> 4/5 escrevendo $CONF"
cat > "$CONF" <<NGINX
# Site institucional (estático) + Sistema (/sistema) no domínio próprio.
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;
    location ^~ /.well-known/acme-challenge/ { root /var/lib/letsencrypt; default_type "text/plain"; }
    location / { return 301 https://$DOMAIN\$request_uri; }
}

# www -> raiz (endereço único, melhor pra SEO e pra sessão do login)
server {
    listen 443 ssl;
    http2 on;
    server_name www.$DOMAIN;
    ssl_certificate     /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    return 301 https://$DOMAIN\$request_uri;
}

server {
    listen 443 ssl;
    http2 on;
    server_name $DOMAIN;

    ssl_certificate     /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_session_cache   shared:SSL:10m;

    include /etc/nginx/conf.d/security-headers.inc;

    # ---------- SISTEMA (mesmas regras do host atual) ----------
    location = /sistema { return 302 /sistema/login; }
    location = /sistema/ { return 302 /sistema/login; }

    # ai-insight: privado por tenant, NUNCA cacheia (anti-vazamento).
    location = /sistema/api/v1/census/ai-insight {
        rewrite ^/sistema/(.*)\$ /\$1 break;
        proxy_pass         http://mn_api;
        proxy_http_version 1.1;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
        include            /etc/nginx/conf.d/security-headers.inc;
    }

    location /sistema/api/v1/census/ {
        rewrite ^/sistema/(.*)\$ /\$1 break;
        proxy_pass         http://mn_api;
        proxy_http_version 1.1;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
        proxy_cache        mn_census;
        proxy_cache_key    "\$uri\$is_args\$args\$enc_bucket";
        proxy_cache_valid  200 7d;
        proxy_ignore_headers Cache-Control Expires;
        proxy_no_cache     \$census_skip_cache;
        proxy_cache_bypass \$census_skip_cache;
        proxy_cache_lock      on;
        proxy_cache_use_stale updating error timeout;
        proxy_cache_background_update on;
        add_header         X-Cache-Status \$upstream_cache_status;
        include            /etc/nginx/conf.d/security-headers.inc;
    }

    # Fotos de candidatos: públicas (chegam via <img>, sem Authorization).
    location ~ ^/sistema/api/v1/tse/candidates/[0-9a-f-]+/photo\$ {
        rewrite ^/sistema/(.*)\$ /\$1 break;
        proxy_pass         http://mn_api;
        proxy_http_version 1.1;
        proxy_set_header   Host              \$host;
        proxy_read_timeout 60s;
        proxy_cache        mn_tse;
        proxy_cache_key    "\$uri";
        proxy_cache_valid  200 7d;
        proxy_cache_valid  404 1h;
        proxy_cache_lock   on;
        add_header         X-Cache-Status \$upstream_cache_status;
        include            /etc/nginx/conf.d/security-headers.inc;
    }

    location /sistema/api/ {
        rewrite ^/sistema/(.*)\$ /\$1 break;
        proxy_pass         http://mn_api;
        proxy_http_version 1.1;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
        client_max_body_size 25m;
        include            /etc/nginx/conf.d/security-headers.inc;
    }

    # Estáticos do Next (imutáveis) — cache longo no browser.
    location /sistema/_next/static/ {
        proxy_pass         http://mn_web;
        proxy_http_version 1.1;
        proxy_set_header   Host \$host;
        add_header         Cache-Control "public, max-age=31536000, immutable";
        include            /etc/nginx/conf.d/security-headers.inc;
    }

    location /sistema {
        proxy_pass         http://mn_web;
        proxy_http_version 1.1;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
        include            /etc/nginx/conf.d/security-headers.inc;
    }

    # ---------- SITE INSTITUCIONAL (estático, SPA) ----------
    root /usr/share/nginx/site;
    index index.html;

    # Assets com hash no nome: cache longo.
    location /assets/ {
        try_files \$uri =404;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }

    # SPA: qualquer rota do site cai no index.html (React Router).
    location / {
        try_files \$uri \$uri/ /index.html;
        add_header Cache-Control "public, max-age=300";
    }
}
NGINX

echo "==> 5/5 validando e recarregando"
docker compose up -d nginx >/dev/null
sleep 3
docker compose exec -T nginx nginx -t
docker compose exec -T nginx nginx -s reload

echo
echo "PRONTO:"
echo "  Site:    https://$DOMAIN"
echo "  Sistema: https://$DOMAIN/sistema/login"
echo "A renovação do certificado já entra no cron existente (seg/qui 4h)."
