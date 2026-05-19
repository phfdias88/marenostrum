#!/usr/bin/env bash
# Testa padroes conhecidos de URL pra foto de candidato TSE.
# Variaveis:
SQ=130001883579
UF=MG
MUNI=47333
ELEI=619
ANO=2024

probe() {
  local url="$1"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" -L --max-time 10 \
    -H "User-Agent: Mozilla/5.0 (MareNostrum)" "$url")
  printf "  [%s] %s\n" "$code" "$url"
}

echo "== Padroes divulgacandcontas =="
probe "https://divulgacandcontas.tse.jus.br/divulga/rest/v1/candidato/$ANO/$SQ"
probe "https://divulgacandcontas.tse.jus.br/divulga/rest/v1/candidato/$ANO/$UF/$MUNI/$ELEI/$SQ"
probe "https://divulgacandcontas.tse.jus.br/dados/$ANO/$UF/$MUNI/$ELEI/foto/$SQ.jpeg"
probe "https://divulgacandcontas.tse.jus.br/dados/$ANO/$UF/$MUNI/$ELEI/$SQ/foto.jpeg"
probe "https://divulgacandcontas.tse.jus.br/dados/$ANO/$UF/$MUNI/$ELEI/$SQ/foto.jpg"
probe "https://divulgacandcontas.tse.jus.br/candidatura/oficial/$ANO/$ELEI/$MUNI/$SQ/$SQ.jpg"
probe "https://divulgacandcontas.tse.jus.br/dados/$ANO/$UF/$MUNI/$ELEI/${SQ}/${SQ}.jpg"
probe "https://divulgacandcontas.tse.jus.br/dados/$ANO/foto/$SQ.jpg"
probe "https://divulgacandcontas.tse.jus.br/divulga/rest/foto/$SQ.jpg"

echo ""
echo "== Padroes CDN sead/odsele =="
probe "https://cdn.tse.jus.br/estatistica/sead/odsele/foto_candidato/foto_candidato_$ANO/$UF/${SQ}.jpg"
probe "https://cdn.tse.jus.br/estatistica/sead/odsele/foto_candidato/foto_candidato_${ANO}_${UF}/${SQ}.jpg"
probe "https://cdn.tse.jus.br/estatistica/sead/odsele/foto_candidato/foto_candidato_$ANO/foto_candidato_${ANO}_${UF}.zip"
probe "https://cdn.tse.jus.br/estatistica/sead/odsele/foto_candidato/foto_candidato_${ANO}_${UF}.zip"

echo ""
echo "== Listar pasta do CDN (HTML index) =="
curl -s --max-time 10 "https://cdn.tse.jus.br/estatistica/sead/odsele/foto_candidato/" \
  | grep -oE 'href="[^"]*"' | head -30 || echo "  (sem index aberto)"

echo ""
echo "== Inspect JSON candidato divulga (HEAD com -i) =="
curl -sL --max-time 10 \
  -H "User-Agent: Mozilla/5.0" \
  "https://divulgacandcontas.tse.jus.br/divulga/rest/v1/candidato/$ANO/$SQ" | head -c 400
echo ""
