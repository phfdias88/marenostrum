#!/usr/bin/env bash
# Varredura do voto POR MUNICIPIO no canal ao vivo do TSE, para varias UFs de
# uma vez, seguida da atualizacao do mapa de vencedores.
#
#   ./scripts/varredura-nacional.sh                       # Brasil, todos os cargos
#   UFS=BA,CE,MG,SP CARGOS=1,3,5 ./scripts/varredura-nacional.sh
#   DATA_PLEITO=25/10/2026 VALIDADE=2026-10-28 CARGOS=1,3 ./scripts/varredura-nacional.sh
#
# POR QUE NAO ESTA NO CRON DE 10 EM 10 MINUTOS: o cron da apuracao so varre os
# municipios do RJ. O Brasil inteiro, com deputado, sao milhoes de linhas e
# horas de banco num servidor de 1 vCPU — coisa para rodar UMA vez, de
# madrugada, nao a cada passada.
#
# O QUE FAZ:
#   1. trava — duas varreduras ao mesmo tempo brigariam pelo unico vCPU;
#   2. captura o voto por municipio (a gravacao SUBSTITUI, entao reexecutar e
#      seguro);
#   3. refaz o mapa de vencedores do ano, que e tabela materializada e nao se
#      atualiza sozinha.
#
# O cache da API e o do nginx NAO sao limpos aqui: o cron do placar
# (apuracao-ao-vivo.sh, de 2 em 2 minutos) ja faz isso a cada passada.
set -uo pipefail

cd "$(dirname "$0")/.."

UFS="${UFS:-TODAS}"
CARGOS="${CARGOS:-1,3,5,6,7,8}"
ANO="${ANO:-2026}"
DATA_PLEITO="${DATA_PLEITO:-04/10/2026}"
# Mesma ideia do apuracao-ao-vivo.sh: depois desta data o script nao faz nada,
# para uma linha de cron esquecida nao bater no TSE para sempre.
VALIDADE="${VALIDADE:-2026-10-07}"
if [[ "$(date +%F)" > "$VALIDADE" ]]; then
  exit 0
fi

LOG="${LOG:-$HOME/varredura-nacional.log}"

exec 9>/tmp/varredura-nacional.lock
if ! flock -n 9; then
  echo "$(date '+%F %T') varredura anterior ainda rodando — saindo" >> "$LOG"
  exit 0
fi

{
  echo "===== $(date '+%F %T') inicio (UFs: $UFS, cargos: $CARGOS, pleito: $DATA_PLEITO)"

  # O script entra por stdin: o arquivo mora no host e sobrevive quando o
  # container da API e recriado por um deploy (o /tmp de dentro dele nao).
  docker compose exec -T -e PYTHONPATH=/app api \
    python - --municipios "$UFS" --cargos "$CARGOS" --data "$DATA_PLEITO" \
    < backend/scripts/apuracao_ao_vivo.py
  rc=$?
  echo "captura terminou com codigo $rc"

  if [ "$rc" -eq 0 ]; then
    docker compose exec -T -e PYTHONPATH=/app api \
      python - --year "$ANO" < backend/scripts/refresh_tse_winners_map.py
    echo "mapa de vencedores terminou com codigo $?"
  fi

  echo "===== $(date '+%F %T') fim"
} >> "$LOG" 2>&1
