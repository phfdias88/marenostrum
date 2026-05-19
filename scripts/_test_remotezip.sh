#!/usr/bin/env bash
# Testa extracao por HTTP Range usando remotezip dentro do container api.
set -e
cd ~/marenostrum
docker compose exec -T api pip install remotezip 2>&1 | tail -3

docker compose exec -T api python3 <<'PY'
import time
from remotezip import RemoteZip

URL = "https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2024/fotos/foto_cand2024_MG_div.zip"
SQ = "130001883579"  # Margarida Salomao

t0 = time.time()
print(f"Conectando ao TSE CDN (Range fetch only)...")
with RemoteZip(URL) as zf:
    t1 = time.time()
    print(f"  Conexao + central dir: {t1-t0:.2f}s")
    names = zf.namelist()
    print(f"  Total arquivos no zip: {len(names)}")
    # Procurar nome contendo o SQ
    matches = [n for n in names if SQ in n]
    print(f"  Matches com {SQ}: {matches}")
    if matches:
        t2 = time.time()
        data = zf.read(matches[0])
        t3 = time.time()
        print(f"  Bytes lidos: {len(data)} em {t3-t2:.2f}s")
        # Salvar pra inspecionar
        with open(f"/tmp/{SQ}.jpg", "wb") as f:
            f.write(data)
        print(f"  Salvo em /tmp/{SQ}.jpg")
        # Detectar header JPEG
        print(f"  Magic bytes: {data[:4].hex()}")
PY

echo ""
echo "== file type =="
docker compose exec -T api file /tmp/130001883579.jpg 2>/dev/null || echo "(file cmd nao disponivel)"
docker compose exec -T api ls -lh /tmp/130001883579.jpg
