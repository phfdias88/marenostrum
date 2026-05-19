#!/usr/bin/env bash
# Dispara sync de votacao_secao_2024 pra uma ou varias UFs sequencialmente.
# Uso: ./scripts/_trigger_secao_uf.sh MG [SP BA ...]
set -e
API="http://localhost/api/v1"
TOKEN=$(curl -fsS -X POST "$API/auth/login" -H "Content-Type: application/json" \
  -d '{"tenant_slug":"marenostrum-admin","email":"admin@marenostrum.com.br","password":"MudeEss@Senha123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
H="Authorization: Bearer $TOKEN"

if [ $# -eq 0 ]; then
  echo "Uso: $0 UF1 [UF2 ...]"
  exit 1
fi

for uf in "$@"; do
  echo ""
  echo "============================================================="
  echo "==  UF=$uf"
  echo "============================================================="

  resp=$(curl -fsS -X POST "$API/tse/sync?dataset=votacao_secao_2024_$uf" -H "$H")
  job_id=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
  echo "Job: $job_id — pollando..."

  # Poll a cada 10s ate completar (status != running/pending)
  while true; do
    sleep 10
    status_json=$(curl -fsS "$API/tse/sync/$job_id" -H "$H")
    status=$(echo "$status_json" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
    rows=$(echo "$status_json" | python3 -c "import sys,json; print(json.load(sys.stdin)['rows_processed'])")
    inserted=$(echo "$status_json" | python3 -c "import sys,json; print(json.load(sys.stdin)['vote_results_imported'])")
    printf "  [%s] rows=%s inserted=%s\n" "$status" "$rows" "$inserted"
    if [ "$status" = "completed" ] || [ "$status" = "failed" ]; then
      if [ "$status" = "failed" ]; then
        echo "  ERRO:"
        echo "$status_json" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error_message',''))" | head -c 500
      fi
      break
    fi
  done
done

echo ""
echo "== TODAS UFs PROCESSADAS =="
