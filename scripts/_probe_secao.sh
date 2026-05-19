#!/usr/bin/env bash
# Usa remotezip pra inspecionar votacao_secao_2024_MG.zip sem baixar tudo
cd ~/marenostrum
docker compose exec -T api python3 <<'PY'
from remotezip import RemoteZip
URL = "https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_secao/votacao_secao_2024_MG.zip"
print("Conectando...")
with RemoteZip(URL) as zf:
    names = zf.namelist()
    print(f"Arquivos: {len(names)}")
    for n in names[:8]:
        print(f"  {n}")
    csvs = [n for n in names if n.lower().endswith('.csv')]
    if csvs:
        sample = csvs[0]
        print(f"\nLendo primeira 4KB de {sample}...")
        # remotezip nao tem stream — pega tudo pra entao retornar so primeiros bytes
        # mas pra um CSV pequeno (header + algumas linhas), nao tem problema:
        data = zf.read(sample)[:4096]
        print(data.decode('latin-1'))
PY
