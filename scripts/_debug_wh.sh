#!/usr/bin/env bash
echo "=== webhook pra UUID zerado, body={} ==="
curl -i -s -X POST "http://localhost/api/v1/webhooks/botconversa/00000000-0000-0000-0000-000000000000" \
    -H "Content-Type: application/json" \
    -H "X-Webhook-Secret: wh-secret-e2e-test" \
    -d '{}'
echo
echo
echo "=== webhook pra UUID zerado, body={\"x\":1} ==="
curl -i -s -X POST "http://localhost/api/v1/webhooks/botconversa/00000000-0000-0000-0000-000000000000" \
    -H "Content-Type: application/json" \
    -H "X-Webhook-Secret: wh-secret-e2e-test" \
    -d '{"x":1}'
