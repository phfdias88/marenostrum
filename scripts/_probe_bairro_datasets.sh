#!/usr/bin/env bash
# Confirma existencia e tamanhos dos datasets necessarios pra mapa por bairro
echo "== eleitorado_local_votacao (LOCAIS + bairros) =="
for url in \
  "https://cdn.tse.jus.br/estatistica/sead/odsele/eleitorado_local_votacao/eleitorado_local_votacao_2024.zip" \
  "https://cdn.tse.jus.br/estatistica/sead/odsele/local_votacao/local_votacao_2024.zip"; do
  code=$(curl -s -o /dev/null -w "%{http_code} size=%{size_download}" -I "$url")
  size=$(curl -sI "$url" | grep -i content-length | awk '{print $2}' | tr -d '\r')
  mb=$([ -n "$size" ] && echo "$((size / 1024 / 1024))MB" || echo "?")
  echo "  [$code] $mb  $url"
done

echo ""
echo "== votacao_secao_2024 (per-secao) — checando se eh por UF =="
for uf in MG SP BA; do
  url="https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_secao/votacao_secao_2024_${uf}.zip"
  size=$(curl -sI "$url" | grep -i content-length | awk '{print $2}' | tr -d '\r')
  mb=$([ -n "$size" ] && echo "$((size / 1024 / 1024))MB" || echo "?")
  code=$(curl -s -o /dev/null -w "%{http_code}" -I "$url")
  echo "  [$code] $mb  $url"
done

echo ""
echo "== CKAN: 'local de votacao' =="
curl -s --max-time 15 "https://dadosabertos.tse.jus.br/api/3/action/package_search?q=local+vota" \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
if d.get('success'):
    for p in d['result']['results'][:5]:
        print(f\"  {p['name']} — {p.get('title','')}\")"

echo ""
echo "== CKAN: package_show eleitorado-local-votacao =="
for slug in eleitorado-local-votacao eleitorado-locais-de-votacao locais-de-votacao votacao-secao; do
  code=$(curl -s -o /tmp/pkg.json -w "%{http_code}" --max-time 10 \
    "https://dadosabertos.tse.jus.br/api/3/action/package_show?id=$slug")
  if [ "$code" = "200" ]; then
    echo "  ENCONTROU: $slug"
    python3 -c "
import json
d=json.load(open('/tmp/pkg.json'))
res=d['result'].get('resources',[])
print(f'  Resources do {sys.argv[1] if False else \"$slug\"}: {len(res)}')
for r in res[:3]:
    print(f\"    [{r.get('format','')}] {r.get('name','')}\")"
  else
    echo "  [$code] $slug"
  fi
done
