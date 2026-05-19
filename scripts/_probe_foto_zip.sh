#!/usr/bin/env bash
# Baixa ZIP de fotos MG, ve tamanho + estrutura, valida Margarida (130001883579)
set -e
DEST=/tmp/foto_mg.zip
URL="https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2024/fotos/foto_cand2024_MG_div.zip"

echo "== HEAD =="
curl -sI "$URL" | head -6

echo ""
echo "== Tamanho + download =="
curl -s -o "$DEST" -w "size=%{size_download} time=%{time_total}s\n" "$URL"
ls -lh "$DEST"

echo ""
echo "== Files dentro do ZIP (primeiros 10 + filtro) =="
unzip -l "$DEST" | head -15
echo "..."
echo "== Procurando 130001883579 (Margarida) =="
unzip -l "$DEST" | grep 130001883579 || echo "NAO ENCONTROU"

echo ""
echo "== Extrair foto da Margarida =="
unzip -p "$DEST" "*130001883579*" > /tmp/margarida.jpg
file /tmp/margarida.jpg
ls -lh /tmp/margarida.jpg
