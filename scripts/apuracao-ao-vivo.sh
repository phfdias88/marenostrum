#!/usr/bin/env bash
# Uma passada da captura ao vivo da apuracao. Feita para rodar de poucos em
# poucos minutos na noite da eleicao (cron), mas funciona igual na mao.
#
#   ./scripts/apuracao-ao-vivo.sh                 # totais do Brasil + municipios do RJ
#   UFS_MUNICIPIO=RJ,SP ./scripts/apuracao-ao-vivo.sh
#   DATA_PLEITO=25/10/2026 ./scripts/apuracao-ao-vivo.sh   # 2o turno
#
# O QUE FAZ, NESTA ORDEM:
#   1. trava — se a passada anterior ainda esta rodando, esta sai sem fazer nada.
#      Duas capturas ao mesmo tempo brigariam pelo unico vCPU e pelas mesmas linhas.
#   2. captura os resultados do canal ao vivo do TSE e grava no banco.
#   3. esvazia o cache de agregacao da API (dura 4h e esconderia o numero novo).
#   4. esvazia o cache do nginx para as rotas de TSE.
#
# Reexecutar e seguro: a captura SUBSTITUI os numeros pelo acumulado, nao soma.
set -uo pipefail

cd "$(dirname "$0")/.."

UFS_MUNICIPIO="${UFS_MUNICIPIO:-RJ}"
DATA_PLEITO="${DATA_PLEITO:-04/10/2026}"
TRAVA="/tmp/apuracao-ao-vivo.lock"
LOG="${LOG:-$HOME/apuracao-ao-vivo.log}"

exec 9>"$TRAVA"
if ! flock -n 9; then
  echo "$(date '+%F %T') passada anterior ainda rodando — pulando" >> "$LOG"
  exit 0
fi

{
  echo "===== $(date '+%F %T') inicio (municipios: $UFS_MUNICIPIO, pleito: $DATA_PLEITO)"

  # O script entra por stdin: o arquivo mora no host, entao sobrevive quando o
  # container da API e recriado por um deploy (o /tmp de dentro dele nao).
  docker compose exec -T -e PYTHONPATH=/app api \
    python - --totais --municipios "$UFS_MUNICIPIO" --data "$DATA_PLEITO" \
    < backend/scripts/apuracao_ao_vivo.py
  rc=$?
  echo "captura terminou com codigo $rc"

  if [ "$rc" -eq 0 ]; then
    # Token de vida curta emitido pelo proprio servidor, so para avisar a API.
    TOKEN=$(docker compose exec -T -e PYTHONPATH=/app api python - <<'PY' 2>/dev/null | tail -1
from datetime import timedelta
from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.models import User
db = SessionLocal()
u = db.query(User).filter(User.is_superadmin.is_(True), User.is_active.is_(True)).first()
role = u.role.value if hasattr(u.role, "value") else str(u.role)
print(create_access_token(user_id=u.id, tenant_id=u.tenant_id, role=role,
                          expires_delta=timedelta(minutes=2)))
PY
)
    if [ -n "$TOKEN" ]; then
      docker compose exec -T api python -c "
import httpx, sys
r = httpx.post('http://localhost:8000/api/v1/tse/ingest/cache-clear',
               headers={'Authorization': 'Bearer ' + sys.argv[1]}, timeout=20)
print('cache da API:', r.status_code, r.text[:60])
" "$TOKEN"
    else
      echo "AVISO: sem token — o cache da API NAO foi limpo"
    fi

    docker compose exec -T nginx sh -c 'rm -rf /var/cache/nginx/tse/*' \
      && echo "cache do nginx (tse) limpo"
  fi

  echo "===== $(date '+%F %T') fim"
} >> "$LOG" 2>&1
