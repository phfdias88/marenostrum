#!/usr/bin/env bash
# ----------------------------------------------------------------------------
# Vigia de disco + backup (MareNostrum) — roda via cron do deploy a cada 30min:
#
#   */30 * * * * /home/deploy/marenostrum/scripts/disk_backup_watch.sh
#
# Sem dependência de SMTP: quando há problema, grava um ALERT.flag (fácil de
# ver por SSH ou por um health-check) e loga. Quando volta ao normal, apaga o
# flag. Se um dia houver webhook/e-mail, é só plugar no bloco marcado.
#
# Gatilhos:
#   - disco em / >= THRESH_PCT (default 85%)
#   - último .dump com mais de MAX_DUMP_H horas (default 26h — o cron é diário)
# ----------------------------------------------------------------------------
set -uo pipefail

THRESH_PCT=85
MAX_DUMP_H=26
DUMP_DIR=/home/deploy/backups
FLAG=/home/deploy/ALERT.flag
LOG=/home/deploy/backups/watch.log

ts=$(date -Is)
alerts=""

# --- disco ---
used=$(df --output=pcent / | tail -1 | tr -dc '0-9')
if [ "${used:-0}" -ge "$THRESH_PCT" ]; then
  alerts="${alerts}disco em ${used}% (limite ${THRESH_PCT}%); "
fi

# --- idade do último dump ---
newest=$(ls -1t "$DUMP_DIR"/marenostrum_*.dump 2>/dev/null | head -1)
if [ -z "${newest:-}" ]; then
  alerts="${alerts}nenhum dump encontrado em ${DUMP_DIR}; "
else
  age_h=$(( ( $(date +%s) - $(stat -c %Y "$newest") ) / 3600 ))
  if [ "$age_h" -gt "$MAX_DUMP_H" ]; then
    alerts="${alerts}último dump tem ${age_h}h (>${MAX_DUMP_H}h); "
  fi
fi

if [ -n "$alerts" ]; then
  echo "${ts} ALERTA: ${alerts}" | tee -a "$LOG"
  echo "${ts} ${alerts}" > "$FLAG"
  # --- PLUGUE AQUI notificação externa quando tiver (webhook/e-mail): ---
  # curl -fsS -m 10 -X POST "$ALERT_WEBHOOK" -d "text=MareNostrum: ${alerts}" >/dev/null 2>&1 || true
else
  echo "${ts} ok: disco ${used}%, último dump recente" >> "$LOG"
  rm -f "$FLAG"
fi

# rotação leve do próprio log (mantém ~500 linhas)
tail -n 500 "$LOG" > "${LOG}.tmp" 2>/dev/null && mv "${LOG}.tmp" "$LOG" 2>/dev/null || true
