#!/usr/bin/env bash
set -e
TOKEN=$(curl -s -X POST http://localhost/api/v1/auth/login \
    -H 'Content-Type: application/json' \
    -d '{"tenant_slug":"marenostrum-admin","email":"admin@marenostrum.com.br","password":"MudeEss@Senha123"}' \
    | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

curl -s http://localhost/api/v1/voting-places/heatmap \
    -H "Authorization: Bearer $TOKEN" > /tmp/heatmap.json

python3 <<'PY'
import json
d = json.loads(open("/tmp/heatmap.json").read())
print("Pontos no heatmap:", len(d["points"]))
print("Total de locais:  ", d["total_places"])
print("Total de votos:   ", d["total_votes"])
print("Pico em um local: ", d["max_votes"], "votos")
if d["points"]:
    p = d["points"][0]
    print("Exemplo de ponto: ", f'{p["name"][:40]}... lat={p["lat"]} lng={p["lng"]} votos={p["votes"]} intensidade={p["intensity"]:.3f}')
PY
