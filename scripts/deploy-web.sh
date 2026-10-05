#!/usr/bin/env bash
# Build e troca do container do frontend, DESACOPLADO do terminal que chamou.
#
#   nohup ./scripts/deploy-web.sh >/dev/null 2>&1 &
#   tail -f /tmp/deploy-web.log        # acaba numa linha "FIM rc=0"
#
# POR QUE EXISTE: o build do Next leva uns 8 minutos neste servidor de 1 vCPU.
# Rodado por dentro de uma sessao ssh, se a sessao cai no meio o build morre
# (ou termina, mas o "up -d" que vinha depois nunca roda e o site fica na
# versao antiga sem ninguem notar). Aconteceu duas vezes na noite de 04/10/2026.
#
# Tudo vai para o log, e a ultima linha diz se deu certo — quem espera so
# precisa procurar por "FIM".
set -uo pipefail

cd "$(dirname "$0")/.."
LOG="${LOG:-/tmp/deploy-web.log}"

{
  echo "===== $(date '+%F %T') inicio"
  docker compose build web
  rc=$?
  echo "build terminou com codigo $rc"
  if [ "$rc" -eq 0 ]; then
    docker compose up -d web
    rc=$?
    sleep 12
    docker compose exec -T nginx nginx -s reload
  fi
  echo "FIM rc=$rc $(date '+%F %T')"
} > "$LOG" 2>&1
