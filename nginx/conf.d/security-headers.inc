# =============================================================================
# Headers de segurança — snippet incluído em TODOS os locations.
#
# Por que um snippet incluído em cada bloco (e não só no server)?
# No nginx, `add_header` NÃO é herdado por um location que tenha `add_header`
# próprio. Como census/tse/_next/imagens têm o seu (X-Cache-Status,
# Cache-Control), eles perderiam o HSTS e os demais headers do server. Incluir
# este arquivo em cada bloco garante o conjunto COMPLETO em todos.
#
# Este arquivo tem extensão .inc de propósito: o nginx.conf faz
# `include /etc/nginx/conf.d/*.conf`, então .inc NÃO é auto-carregado —
# só entra onde eu explicitamente der `include`.
# =============================================================================

# Força HTTPS por ~6 meses (inclui subdomínios). 'always' = manda até em erro.
add_header Strict-Transport-Security "max-age=15768000; includeSubDomains" always;

# Impede o navegador de "adivinhar" o content-type (anti MIME-sniffing).
add_header X-Content-Type-Options "nosniff" always;

# Anti-clickjacking (browsers antigos). O CSP frame-ancestors cobre os modernos.
add_header X-Frame-Options "SAMEORIGIN" always;

# Não vaza a URL interna (com IDs) pra sites de terceiros ao clicar em links.
add_header Referrer-Policy "strict-origin-when-cross-origin" always;

# Content-Security-Policy — a principal mitigação contra roubo de token por XSS.
# connect-src 'self'  -> XSS não consegue mandar fetch/XHR/beacon pra fora.
# img-src enumerado    -> nem exfiltrar via <img src="evil?token">.
# object-src 'none' / base-uri 'self' / frame-ancestors 'self' -> travas padrão.
# 'unsafe-inline'/'unsafe-eval' seguem liberados pro Next hidratar (endurecer
# com nonce é trabalho futuro, mas não afeta a trava de exfiltração acima).
#
# img-src inclui os tile servers dos mapas (CartoDB voyager/dark, satélite
# ArcGIS) + fotos/logos do TSE. Se adicionar uma nova camada de mapa, o host
# do tile precisa entrar aqui.
# frame-src 'self': o embed de sistema externo (EmbeddedFrame / Sonar) está em
# placeholder (example.com, não carrega). Se um dia ligar um Looker/Metabase/
# Sonar real, adicione o host dele em frame-src OU o iframe fica em branco.
add_header Content-Security-Policy "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'self'; frame-src 'self'; img-src 'self' data: blob: https://*.basemaps.cartocdn.com https://server.arcgisonline.com https://cdn.tse.jus.br; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:" always;
