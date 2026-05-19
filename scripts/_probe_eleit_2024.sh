#!/usr/bin/env bash
curl -s --max-time 15 "https://dadosabertos.tse.jus.br/api/3/action/package_show?id=eleitorado-2024" > /tmp/el.json
python3 <<'PY'
import json
d = json.load(open('/tmp/el.json'))
res = d['result'].get('resources', [])
print(f"Total resources: {len(res)}")
print()
print("=== Recursos com 'local' ou 'secao' ou 'bairro' ===")
for r in res:
    nm = r.get('name', '')
    if any(k in nm.lower() for k in ['local', 'secao', 'bairro', 'sessao']):
        print(f"  [{r.get('format',''):>5}] {nm}")
        print(f"     {r.get('url','')}")
print()
print("=== Todos os outros recursos ===")
for r in res[:30]:
    nm = r.get('name', '')
    if not any(k in nm.lower() for k in ['local', 'secao', 'bairro', 'sessao']):
        print(f"  [{r.get('format',''):>5}] {nm}")
PY
