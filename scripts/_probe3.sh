#!/usr/bin/env bash
# Inspeciona resources do pacote candidatos-2024
set -e
echo "== Resources de candidatos-2024 =="
curl -s --max-time 15 "https://dadosabertos.tse.jus.br/api/3/action/package_show?id=candidatos-2024" \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
if not d.get('success'):
    print('Erro')
    sys.exit(1)
res=d['result'].get('resources',[])
print(f'Total resources: {len(res)}')
for r in res:
    name=r.get('name','')
    fmt=r.get('format','')
    url=r.get('url','')
    if 'foto' in name.lower() or 'foto' in url.lower() or fmt.lower() in ('zip','jpg','jpeg','png'):
        print(f'  [{fmt:>6s}] {name}')
        print(f'           {url}')
print()
print('--- Todos resources (top 30):')
for r in res[:30]:
    print(f\"  [{r.get('format',''):>6s}] {r.get('name','')[:60]:<60s} -> {r.get('url','')[:120]}\")"
