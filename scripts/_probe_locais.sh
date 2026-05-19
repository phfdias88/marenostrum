#!/usr/bin/env bash
echo "== CKAN: search eleitorado 2024 =="
curl -s --max-time 15 "https://dadosabertos.tse.jus.br/api/3/action/package_search?q=eleitorado&rows=20" \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
if d.get('success'):
    for p in d['result']['results'][:20]:
        print(f\"  {p['name']} — {p.get('title','')}\")"

echo ""
echo "== eleitorado-locais-votacao variants =="
for slug in eleitorado-locais-votacao eleitorado-secao-2024 secoes-votacao locais-secao; do
  code=$(curl -s -o /tmp/p.json -w "%{http_code}" --max-time 10 \
    "https://dadosabertos.tse.jus.br/api/3/action/package_show?id=$slug")
  if [ "$code" = "200" ]; then
    echo "ENCONTROU: $slug"
    python3 -c "
import json
d=json.load(open('/tmp/p.json'))
res=d['result'].get('resources',[])
print(f'Resources: {len(res)}')
for r in res[:5]:
    print(f\"  [{r.get('format','')}] {r.get('name','')}\")
    print(f\"     {r.get('url','')}\")"
  fi
done

echo ""
echo "== eleitorado-municipio-zona =="
curl -s --max-time 10 \
  "https://dadosabertos.tse.jus.br/api/3/action/package_show?id=eleitorado-municipio-zona" \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
if d.get('success'):
    res=d['result'].get('resources',[])
    print(f'Resources: {len(res)}')
    for r in res[:8]:
        nm=r.get('name','')
        if '2024' in nm or 'eleitor' in nm.lower() or 'local' in nm.lower():
            print(f\"  [{r.get('format','')}] {nm}\")
            print(f\"     {r.get('url','')}\")"
