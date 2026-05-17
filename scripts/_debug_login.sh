#!/usr/bin/env bash
echo "=== LOGIN response cru ==="
curl -i -s -X POST http://localhost/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"tenant_slug":"marenostrum-admin","email":"admin@marenostrum.local","password":"MudeEss@Senha123"}'
echo
echo "=== /me sem token (deve 401) ==="
curl -i -s http://localhost/api/v1/auth/me
