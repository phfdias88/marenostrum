#!/usr/bin/env bash
set -e
curl -fsS http://localhost/api/openapi.json -o /tmp/openapi.json
python3 - <<'PY'
import json
d = json.load(open('/tmp/openapi.json'))
tse_paths = sorted(p for p in d['paths'] if '/tse' in p)
print(f"== {len(tse_paths)} TSE endpoints ==")
for p in tse_paths:
    methods = sorted(d['paths'][p].keys())
    print(f"  {','.join(m.upper() for m in methods):14s} {p}")
print()
print("Tags:", [t['name'] for t in d.get('tags', [])])
PY
