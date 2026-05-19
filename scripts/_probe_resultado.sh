#!/usr/bin/env bash
set -e
cd ~/marenostrum
URL="https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/votacao_candidato_munzona_2024.zip"
echo "Baixando..."
curl -sL -o /tmp/cand.zip "$URL"
ls -lh /tmp/cand.zip
docker compose cp /tmp/cand.zip api:/tmp/cand.zip
docker compose exec -T api python3 <<'PY'
import zipfile, csv, io
zf = zipfile.ZipFile('/tmp/cand.zip')
# Pega o primeiro CSV nacional (BRASIL) ou qualquer um
names = [n for n in zf.namelist() if n.lower().endswith('.csv')]
print("CSVs:", names[:5])
name = names[0]
with zf.open(name) as f:
    txt = io.TextIOWrapper(f, encoding='latin-1', newline='')
    reader = csv.DictReader(txt, delimiter=';')
    cols = reader.fieldnames
    print("\nColunas com SIT/TURNO/ELE:")
    for c in cols:
        if any(k in c.upper() for k in ['SIT','TURNO','ELE','RESULT']):
            print(f"  {c}")
    print("\nAmostra:")
    for i, row in enumerate(reader):
        if i >= 6: break
        print(f"  {row.get('NM_URNA_CANDIDATO','')[:25]:25s} | cargo={row.get('DS_CARGO','')[:10]:10s} | cand_sit={row.get('DS_SITUACAO_CANDIDATURA','')!r} | tot_turno={row.get('DS_SIT_TOT_TURNO','')!r}")
PY
