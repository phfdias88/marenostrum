#!/usr/bin/env bash
set -e
URL="https://cdn.tse.jus.br/estatistica/sead/odsele/eleitorado_locais_votacao/eleitorado_local_votacao_2024.zip"
echo "== HEAD =="
curl -sI "$URL" | head -8
echo ""
echo "== Baixando (~50MB?) =="
curl -s -o /tmp/locais.zip -w "size=%{size_download} time=%{time_total}s\n" "$URL"
ls -lh /tmp/locais.zip
echo ""
echo "== Conteudo do ZIP =="
unzip -l /tmp/locais.zip | head -20
echo ""
echo "== Estrutura do CSV (header + 3 linhas) — buscando coluna BAIRRO =="
CSV_NAME=$(unzip -l /tmp/locais.zip | awk '{print $4}' | grep -i '\.csv$' | head -1)
echo "CSV: $CSV_NAME"
unzip -p /tmp/locais.zip "$CSV_NAME" | iconv -f latin1 -t utf-8 | head -3
echo ""
echo "== Procurando bairro/endereco/numero secao no header =="
unzip -p /tmp/locais.zip "$CSV_NAME" | iconv -f latin1 -t utf-8 | head -1 | tr ';' '\n' | grep -iE 'bair|endereco|secao|cep|nm_'
