#!/usr/bin/env bash
# =============================================================================
# Coloca o SISTEMA num domínio próprio (ex: app.marenostrumconsult.com.br),
# independente do site institucional.
#
# POR QUÊ: hoje o /sistema depende do rewrite da Vercel no domínio principal.
# Quando o DNS do domínio saiu da Vercel (incidente jul/2026), o sistema ficou
# inacessível pelo endereço bonito. Com subdomínio próprio apontando DIRETO
# para esta VPS, o sistema para de depender de onde o site está hospedado.
#
# PRÉ-REQUISITO (feito no painel do domínio, 1 registro):
#   Tipo A   app   ->   72.60.248.41
#   Confirme a propagação:  nslookup app.marenostrumconsult.com.br
#
# USO (na VPS, dentro de ~/marenostrum):
#   bash scripts/setup-app-subdomain.sh app.marenostrumconsult.com.br seu@email.com
# =============================================================================
set -euo pipefail

DOMAIN="${1:?informe o domínio, ex: app.marenostrumconsult.com.br}"
# Sem apostrofo na mensagem: dentro de ${2:?...} o bash trata o ' como abertura
# de string e engole a linha seguinte (o script morria com "unbound variable").
EMAIL="${2:?informe um e-mail para avisos do Lets Encrypt}"
CONF="nginx/conf.d/app-subdomain.conf"

cd "$(dirname "$0")/.."

echo "==> 1/4 conferindo se o DNS já aponta para esta máquina"
IP_LOCAL="$(curl -s https://api.ipify.org || echo '')"
IP_DNS="$(getent hosts "$DOMAIN" | awk '{print $1}' | head -1 || echo '')"
if [ -z "$IP_DNS" ]; then
  echo "ERRO: $DOMAIN não resolve. Crie o registro A antes de rodar." >&2
  exit 1
fi
if [ -n "$IP_LOCAL" ] && [ "$IP_DNS" != "$IP_LOCAL" ]; then
  echo "ERRO: $DOMAIN aponta para $IP_DNS, mas esta VPS é $IP_LOCAL." >&2
  echo "      Corrija o registro A (ou aguarde a propagação) e rode de novo." >&2
  exit 1
fi
echo "    OK: $DOMAIN -> $IP_DNS"

echo "==> 2/4 emitindo certificado (Let's Encrypt, modo standalone)"
# O nginx precisa liberar a porta 80 durante a validação — mesmo método do
# cron de renovação já existente.
docker compose stop nginx >/dev/null 2>&1 || true
docker run --rm -p 80:80 \
  -v /etc/letsencrypt:/etc/letsencrypt \
  -v /var/lib/letsencrypt:/var/lib/letsencrypt \
  certbot/certbot certonly --standalone \
  -d "$DOMAIN" --agree-tos -m "$EMAIL" --no-eff-email --non-interactive

echo "==> 3/4 escrevendo $CONF"
# Serve o MESMO app (/sistema) no domínio próprio. Fora do /sistema, manda pro
# login — quem digitar só o domínio cai direto na tela de entrada.
cat > "$CONF" <<NGINX
server {
    listen 80;
    server_name $DOMAIN;
    location ^~ /.well-known/acme-challenge/ { root /var/lib/letsencrypt; default_type "text/plain"; }
    location / { return 301 https://\$host\$request_uri; }
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

    # Raiz do subdomínio -> tela de login do sistema.
    location = / { return 302 /sistema/login; }

    # API do sistema: tira o /sistema (o container recebe /api/* nativo).
    location /sistema/api/ {
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

    # App Next (basePath /sistema): mantém o prefixo.
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
}
NGINX

echo "==> 4/4 validando e recarregando o nginx"
docker compose up -d nginx >/dev/null
sleep 3
docker compose exec -T nginx nginx -t
docker compose exec -T nginx nginx -s reload

echo
echo "PRONTO. Teste:  https://$DOMAIN/sistema/login"
echo "A renovação automática do certificado já cobre este domínio"
echo "(o cron de seg/qui roda 'certbot renew' pra TODOS os certificados)."
