#!/usr/bin/env bash
# Marca jobs TSE presos em 'running' como 'failed', pra liberar novo sync.
set -e
cd ~/marenostrum
docker compose exec -T db psql -U marenostrum -d marenostrum <<'SQL'
UPDATE tse_sync_jobs
SET status='failed',
    error_message='Stale: integer overflow on sq_candidato (fixed in 007)',
    completed_at=now()
WHERE status IN ('pending','running');
SELECT id, status, error_message FROM tse_sync_jobs;
SQL
