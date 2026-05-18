#!/usr/bin/env bash
echo "=== tenants no DB ==="
docker compose -f /home/deploy/marenostrum/docker-compose.yml exec -T db psql -U marenostrum -d marenostrum -c "SELECT slug, name FROM tenants;"
echo
echo "=== users no DB ==="
docker compose -f /home/deploy/marenostrum/docker-compose.yml exec -T db psql -U marenostrum -d marenostrum -c "SELECT email, role FROM users;"
echo
echo "=== re-cria tenant B ==="
TENANT_SLUG=tenant-b-e2e \
TENANT_NAME='Tenant B E2E' \
ADMIN_EMAIL=b@example.com \
ADMIN_NAME='Admin B' \
ADMIN_PASSWORD='SenhaB@123456' \
/home/deploy/marenostrum/scripts/seed-admin.sh 2>&1 | tail -8
echo
echo "=== tenta login B ==="
curl -i -s -X POST http://localhost/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"tenant_slug":"tenant-b-e2e","email":"b@example.com","password":"SenhaB@123456"}'
echo
echo "=== cleanup ==="
docker compose -f /home/deploy/marenostrum/docker-compose.yml exec -T db psql -U marenostrum -d marenostrum -c "
DELETE FROM interactions WHERE tenant_id IN (SELECT id FROM tenants WHERE slug='tenant-b-e2e');
DELETE FROM users WHERE tenant_id IN (SELECT id FROM tenants WHERE slug='tenant-b-e2e');
DELETE FROM tenants WHERE slug='tenant-b-e2e';
" 2>&1
