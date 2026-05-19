#!/usr/bin/env bash
# Probe 2: descobre a estrutura real do CDN TSE
echo "== Tentando listar CDN root =="
curl -s --max-time 10 "https://cdn.tse.jus.br/" -o /tmp/cdn_root.html -w "code=%{http_code} size=%{size_download}\n"

echo ""
echo "== CKAN: package_search 'foto' =="
curl -s --max-time 15 "https://dadosabertos.tse.jus.br/api/3/action/package_search?q=foto" \
  | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    if d.get('success'):
        for p in d['result']['results'][:10]:
            print(f\"  {p['name']} — {p.get('title','')}\")
    else:
        print('Falha')
except Exception as e:
    print('err:', e)"

echo ""
echo "== CKAN: package_show fotos =="
for slug in foto-de-candidato fotos-de-candidatos fotos-candidatos foto_candidato fotos_candidatos foto-candidato; do
  code=$(curl -s -o /tmp/pkg.json -w "%{http_code}" --max-time 10 \
    "https://dadosabertos.tse.jus.br/api/3/action/package_show?id=$slug")
  echo "  [$code] $slug"
  if [ "$code" = "200" ]; then
    python3 -c "
import json
d=json.load(open('/tmp/pkg.json'))
if d.get('success'):
    print('  Title:', d['result'].get('title'))
    print('  Resources:')
    for r in d['result'].get('resources',[])[:5]:
        print(f\"    - {r.get('name')} | {r.get('format')} | {r.get('url')}\")"
    break
  fi
done

echo ""
echo "== Probe direto CDN com listing diretorios conhecidos =="
for path in "/estatistica/sead/odsele/foto_candidato/" "/estatistica/sead/odsele/fotos_candidatos/" "/divulga/" "/divulga/oficial/"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://cdn.tse.jus.br${path}")
  echo "  [$code] https://cdn.tse.jus.br${path}"
done
