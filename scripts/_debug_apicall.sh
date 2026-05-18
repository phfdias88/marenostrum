#!/usr/bin/env bash
set -uo pipefail
BASE=http://localhost

api_call() {
    local method="$1" path="$2"
    local args=(-s -o /tmp/lb -w '%{http_code}' -X "$method" "$BASE$path" -H "Content-Type: application/json")
    curl "${args[@]}" > /tmp/last_status
    cat /tmp/lb
}
LAST_STATUS() { cat /tmp/last_status; }

echo "=== chamada 1 (health) ==="
B=$(api_call GET /api/health)
echo "body=$B"
echo "status (subshell): $(LAST_STATUS)"
echo "status (direto):"
cat /tmp/last_status
echo
echo "stat /tmp/last_status:"
ls -la /tmp/last_status
