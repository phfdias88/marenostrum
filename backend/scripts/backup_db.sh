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
#
# Restaurar (exemplo):
#   docker compose exec -T db pg_restore -U marenostrum -d marenostrum \
#     --clean --if-exists < /home/deploy/backups/marenostrum_YYYY-MM-DD.dump
# ----------------------------------------------------------------------------
set -euo pipefail

COMPOSE_DIR=/home/deploy/marenostrum
BACKUP_DIR=/home/deploy/backups
KEEP=3              # quantos dumps manter (ver tamanho × disco livre)
MIN_FREE_GB=3       # não roda com menos que isso livre
MIN_DUMP_MB=200     # dump menor que isso = algo errado, não rotaciona

log() { echo "$(date -Is) $*"; }

mkdir -p "$BACKUP_DIR"
cd "$COMPOSE_DIR"

free_kb=$(df --output=avail / | tail -1 | tr -d ' ')
if [ "$free_kb" -lt $((MIN_FREE_GB * 1024 * 1024)) ]; then
  log "ABORT: disco insuficiente ($((free_kb / 1024 / 1024))GB livres, mínimo ${MIN_FREE_GB}GB)"
  exit 1
fi

stamp=$(date +%F)
out="$BACKUP_DIR/marenostrum_${stamp}.dump"

log "iniciando pg_dump -> $out"
docker compose exec -T db pg_dump -U marenostrum -d marenostrum -Fc > "${out}.part"

# valida antes de promover: header do formato custom + tamanho plausível
size_mb=$(( $(stat -c %s "${out}.part") / 1024 / 1024 ))
header=$(head -c 5 "${out}.part")
if [ "$header" != "PGDMP" ] || [ "$size_mb" -lt "$MIN_DUMP_MB" ]; then
  log "FALHOU: dump inválido (header='$header', ${size_mb}MB) — mantendo backups antigos"
  rm -f "${out}.part"
  exit 1
fi
mv "${out}.part" "$out"
log "ok: ${size_mb}MB"

# rotação: mantém os KEEP mais recentes
ls -1t "$BACKUP_DIR"/marenostrum_*.dump 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
log "rotação concluída ($(ls -1 "$BACKUP_DIR"/marenostrum_*.dump | wc -l) dumps mantidos)"
