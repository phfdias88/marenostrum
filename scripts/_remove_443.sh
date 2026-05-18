#!/usr/bin/env bash
# Remove a publicacao da porta 443 do nginx no docker-compose.yml
# (browser HTTPS-first trava porque nginx nao tem TLS — RST imediato em 443
# faz browser fallback pra HTTP automaticamente)
set -euo pipefail

cd /home/deploy/marenostrum
cp -n docker-compose.yml docker-compose.yml.bak 2>/dev/null || true

python3 <<'PY'
import re
path = "docker-compose.yml"
with open(path) as f:
    content = f.read()
# Remove a linha "      - \"443:443\"" preservando indentacao
new = re.sub(r'\n\s*-\s*"443:443"\s*\n', '\n', content)
if new == content:
    print("[INFO] Nada removido — pode ja estar fora")
else:
    with open(path, "w") as f:
        f.write(new)
    print("[OK] linha 443:443 removida")
PY

echo "=== ports do nginx no compose ==="
grep -A4 "nginx:" docker-compose.yml | grep -E "ports|443|80" || true

echo "=== recreate nginx ==="
docker compose up -d --force-recreate nginx 2>&1 | tail -5

sleep 2
echo "=== porta 443 (deve estar VAZIO) ==="
sudo ss -tlnp 'sport = :443' 2>/dev/null || echo "(nada listening)"
echo "=== porta 80 (deve continuar) ==="
sudo ss -tlnp 'sport = :80' 2>/dev/null
