#!/usr/bin/env bash
# Adiciona pg_trgm + GIN indexes pra acelerar ILIKE em candidatos/municipios.
cd ~/marenostrum
echo "== 2022 import status =="
docker compose exec -T db psql -U marenostrum -d marenostrum -tA -c \
  "SELECT dataset,status,vote_results_imported FROM tse_sync_jobs WHERE dataset='candidato_munzona_2022' ORDER BY created_at DESC LIMIT 1;"

echo ""
echo "== CREATE EXTENSION pg_trgm =="
docker compose exec -T db psql -U marenostrum -d marenostrum -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"

echo ""
echo "== GIN trigram indexes (urn_name, name, municipios.name) =="
docker compose exec -T db psql -U marenostrum -d marenostrum -c "
CREATE INDEX IF NOT EXISTS ix_tse_candidates_urn_trgm ON tse_candidates USING gin (urn_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_tse_candidates_name_trgm ON tse_candidates USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_tse_municipalities_name_trgm ON tse_municipalities USING gin (name gin_trgm_ops);
"
echo ""
echo "== ANALYZE =="
docker compose exec -T db psql -U marenostrum -d marenostrum -c "ANALYZE tse_candidates; ANALYZE tse_municipalities;"

echo ""
echo "== EXPLAIN apos indice (count de 'silva') =="
docker compose exec -T db psql -U marenostrum -d marenostrum -c "
EXPLAIN ANALYZE SELECT count(*) FROM tse_candidates WHERE urn_name ILIKE '%silva%' OR name ILIKE '%silva%';" 2>&1 | tail -8
