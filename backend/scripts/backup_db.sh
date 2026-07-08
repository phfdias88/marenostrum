#!/usr/bin/env bash
# ----------------------------------------------------------------------------
# Backup diário do Postgres (MareNostrum) — roda via cron do usuário deploy.
#
#   30 3 * * * /home/deploy/marenostrum/scripts/backup_db.sh
#
# - pg_dump em formato custom (-Fc): comprimido e restaurável seletivamente
#   com pg_restore (tabela a tabela se preciso).
# - Guarda de disco: aborta se houver menos de MIN_FREE_GB livres — numa VPS
#   de 48GB é melhor ficar sem o backup do dia do que derrubar o Postgres
#   por disco cheio.
# - Rotação: mantém os KEEP dumps mais recentes; o resto é apagado.
# - Validação: header PGDMP + tamanho mínimo (dump truncado não conta).
# - OFF-SITE + ALERTA (opcionais, env-gated): ver bloco de config abaixo. Sem
#   as vars, o script se comporta EXATAMENTE como antes (só backup local).
#
# Restaurar (exemplo):
#   docker compose exec -T db pg_restore -U marenostrum -d marenostrum \
#     --clean --if-exists < /home/deploy/backups/marenostrum_YYYY-MM-DD.dump
# ----------------------------------------------------------------------------
set -euo pipefail

COMPOSE_DIR=/home/deploy/marenostrum
BACKUP_DIR=/home/deploy/backups
KEEP=3              # quantos dumps LOCAIS manter (ver tamanho × disco livre)
MIN_FREE_GB=3       # não roda com menos que isso livre
MIN_DUMP_MB=200     # dump menor que isso = algo errado, não rotaciona

# --- Config OPCIONAL de off-site + alerta (env-gated) -----------------------
# Defina no ambiente ou em $COMPOSE_DIR/.backup.env (NÃO versionar — tem URLs
# com segredo). Todas inertes se não setadas:
#   ALERT_WEBHOOK          URL que recebe POST JSON {"text":"..."} em caso de
#                          falha (Slack; p/ Discord use a URL com sufixo /slack).
#   HEARTBEAT_URL          dead-man's-switch (ex.: healthchecks.io). Ping em
#                          sucesso; ping em "${HEARTBEAT_URL}/fail" em falha —
#                          alerta se o backup DEIXAR de rodar.
#   OFFSITE_RCLONE_REMOTE  remote rclone p/ cópia off-site, ex.:
#                          "mncrypt:marenostrum-backups". Use um remote do tipo
#                          CRYPT pra cifrar em repouso fora da VPS.
#   OFFSITE_KEEP           retenção off-site (default 14).
ENV_FILE="$COMPOSE_DIR/.backup.env"
if [ -f "$ENV_FILE" ]; then set -a; . "$ENV_FILE"; set +a; fi
ALERT_WEBHOOK="${ALERT_WEBHOOK:-}"
HEARTBEAT_URL="${HEARTBEAT_URL:-}"
OFFSITE_RCLONE_REMOTE="${OFFSITE_RCLONE_REMOTE:-}"
OFFSITE_KEEP="${OFFSITE_KEEP:-14}"

log() { echo "$(date -Is) $*"; }

notify() {  # $1 = mensagem — best-effort, nunca derruba o script
  [ -n "$ALERT_WEBHOOK" ] || return 0
  curl -fsS -m 10 -H 'Content-Type: application/json' \
    -d "{\"text\": \"[MareNostrum backup] $1\"}" "$ALERT_WEBHOOK" >/dev/null 2>&1 || true
}
heartbeat() {  # $1 = "" (sucesso) ou "/fail"
  [ -n "$HEARTBEAT_URL" ] || return 0
  curl -fsS -m 10 "${HEARTBEAT_URL}${1:-}" >/dev/null 2>&1 || true
}
fail() {  # $1 = mensagem -> loga, notifica, sinaliza heartbeat/fail, sai 1
  log "FALHOU: $1"
  notify "FALHOU — $1"
  heartbeat /fail
  exit 1
}

mkdir -p "$BACKUP_DIR"
cd "$COMPOSE_DIR"

free_kb=$(df --output=avail / | tail -1 | tr -d ' ')
if [ "$free_kb" -lt $((MIN_FREE_GB * 1024 * 1024)) ]; then
  fail "disco insuficiente ($((free_kb / 1024 / 1024))GB livres, mínimo ${MIN_FREE_GB}GB)"
fi

stamp=$(date +%F)
out="$BACKUP_DIR/marenostrum_${stamp}.dump"

log "iniciando pg_dump -> $out"
docker compose exec -T db pg_dump -U marenostrum -d marenostrum -Fc > "${out}.part" \
  || fail "pg_dump retornou erro"

# valida antes de promover: header do formato custom + tamanho plausível
size_mb=$(( $(stat -c %s "${out}.part") / 1024 / 1024 ))
header=$(head -c 5 "${out}.part")
if [ "$header" != "PGDMP" ] || [ "$size_mb" -lt "$MIN_DUMP_MB" ]; then
  rm -f "${out}.part"
  fail "dump inválido (header='$header', ${size_mb}MB) — mantendo backups antigos"
fi
mv "${out}.part" "$out"
log "ok local: ${size_mb}MB"

# rotação local: mantém os KEEP mais recentes
ls -1t "$BACKUP_DIR"/marenostrum_*.dump 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
log "rotação local concluída ($(ls -1 "$BACKUP_DIR"/marenostrum_*.dump | wc -l) dumps mantidos)"

# --- OFF-SITE (opcional) ----------------------------------------------------
# Só local NÃO é backup de desastre: se a VPS morrer, banco e dumps somem
# juntos. Quando OFFSITE_RCLONE_REMOTE está setado, sobe o dump do dia p/ fora.
if [ -n "$OFFSITE_RCLONE_REMOTE" ]; then
  if command -v rclone >/dev/null 2>&1; then
    log "off-site: rclone copy -> $OFFSITE_RCLONE_REMOTE"
    if rclone copyto -q "$out" "$OFFSITE_RCLONE_REMOTE/marenostrum_${stamp}.dump"; then
      # retenção off-site: apaga os mais antigos além de OFFSITE_KEEP
      rclone lsf "$OFFSITE_RCLONE_REMOTE" 2>/dev/null \
        | grep -E '^marenostrum_.*\.dump$' | sort | head -n "-${OFFSITE_KEEP}" \
        | while read -r f; do rclone deletefile -q "$OFFSITE_RCLONE_REMOTE/$f" || true; done
      log "off-site ok"
    else
      # off-site falhou mas o backup LOCAL do dia está OK: avisa, não aborta.
      log "AVISO: off-site falhou (backup local preservado)"
      notify "AVISO — cópia off-site falhou (backup local do dia OK)"
      heartbeat /fail
      exit 0
    fi
  else
    log "AVISO: OFFSITE_RCLONE_REMOTE setado mas rclone não instalado"
    notify "AVISO — rclone não instalado; off-site não rodou"
  fi
fi

heartbeat
log "concluído"
