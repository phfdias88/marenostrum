#!/usr/bin/env bash
# Gera .env (raiz e backend) com secrets aleatorios.
# Idempotente: se .env ja existe, NAO sobrescreve (preserva secrets em uso).
set -euo pipefail

cd /home/deploy/marenostrum

# --- .env da RAIZ (build args do Next) ---
if [[ ! -f .env ]]; then
    cat > .env <<'EOF'
# Build args do Next.js (NEXT_PUBLIC_* inlinados no bundle do cliente)
NEXT_PUBLIC_API_URL=http://72.60.248.41/api
NEXT_PUBLIC_ANALYTICS_URL=https://example.com/analytics
NEXT_PUBLIC_SONAR_URL=https://example.com/sonar
EOF
    chown deploy:deploy .env
    chmod 600 .env
    echo "OK .env raiz criado"
else
    echo "INFO .env raiz ja existia, mantido"
fi

# --- backend/.env (secrets de runtime) ---
if [[ ! -f backend/.env ]]; then
    JWT=$(openssl rand -hex 32)
    PGPASS=$(openssl rand -base64 24 | tr -d '/+=' | head -c 32)

    cat > backend/.env <<EOF
APP_ENV=production
APP_NAME=MareNostrum API

# Postgres (bate com docker-compose.yml)
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=marenostrum
POSTGRES_USER=marenostrum
POSTGRES_PASSWORD=${PGPASS}

# JWT
JWT_SECRET_KEY=${JWT}
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60

# CORS - libera o IP da VPS
CORS_ORIGINS=["http://72.60.248.41","http://localhost:3000"]

# Webhook secret global (fallback de dev — produção usa per-tenant)
WEBHOOK_GLOBAL_SECRET=$(openssl rand -hex 24)

# Nominatim
NOMINATIM_USER_AGENT=MareNostrum/0.1 (admin@marenostrum.local)
NOMINATIM_BASE_URL=https://nominatim.openstreetmap.org
GEOCODING_DEFAULT_CITY=Juiz de Fora
GEOCODING_DEFAULT_STATE=MG
EOF
    chown deploy:deploy backend/.env
    chmod 600 backend/.env
    echo "OK backend/.env criado"
    echo "POSTGRES_PASSWORD=$PGPASS"  # mostrado uma vez pra registro
else
    echo "INFO backend/.env ja existia, mantido"
fi

# --- frontend/.env (so' pra compatibilidade — build usa o .env da raiz) ---
if [[ ! -f frontend/.env ]]; then
    cp frontend/.env.example frontend/.env
    chown deploy:deploy frontend/.env
    echo "OK frontend/.env criado"
fi
