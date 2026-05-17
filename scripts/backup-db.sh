#!/usr/bin/env bash
# =============================================================================
# Backup diario do Postgres (rode via cron na VPS).
# Mantem 7 dias locais. Recomenda-se espelhar /var/backups/marenostrum para
# storage externo (S3/Backblaze/rsync) - ver bloco comentado no final.
# =============================================================================
set -euo pipefail

BACKUP_DIR="/var/backups/marenostrum"
RETENTION_DAYS=7
TS="$(date +%Y%m%d_%H%M%S)"
FILE="$BACKUP_DIR/marenostrum_${TS}.sql.gz"

mkdir -p "$BACKUP_DIR"

# pg_dump rodando DENTRO do container db (nao precisa de psql no host)
docker exec mn_db pg_dump \
    -U "${POSTGRES_USER:-marenostrum}" \
    -d "${POSTGRES_DB:-marenostrum}" \
    --clean --if-exists --no-owner \
    | gzip -9 > "$FILE"

# Rotacao: apaga backups antigos
find "$BACKUP_DIR" -type f -name "marenostrum_*.sql.gz" -mtime +$RETENTION_DAYS -delete

echo "[$(date -Iseconds)] backup ok: $FILE ($(du -h "$FILE" | cut -f1))"

# -- OFFSITE (descomente quando tiver bucket configurado) -------------------
# aws s3 cp "$FILE" "s3://marenostrum-backups/db/" --storage-class STANDARD_IA
# OU rsync para outro servidor:
# rsync -az "$FILE" backup@outro-host:/backups/marenostrum/
