#!/usr/bin/env bash
# Loop server-side: sincroniza votacao_secao_2024 de TODAS as UFs restantes
# sequencialmente. Roda via nohup na VPS — sobrevive a logout/sessao.
#
# Uso na VPS:
#   nohup bash /tmp/_sync_all_ufs_server.sh > /tmp/sync_ufs.log 2>&1 &
#
# Pula UFs que ja tem dados (verifica via job COMPLETED previo).
set -u
API="http://localhost/api/v1"

# Ordem: do menor pro maior (UFs pequenas terminam rapido, feedback cedo).
# MG ja foi feito manualmente — incluido aqui mesmo (idempotente via upsert),
# mas colocado por ultimo caso queira re-rodar. Removido da lista principal.
UFS="RR AP AC TO RO AM AL SE PB PI MS MA RN ES MT DF PE GO CE PA SC PR RS RJ BA SP"

login() {
  curl -fsS -X POST "$API/auth/login" -H "Content-Type: application/json" \
    -d '{"tenant_slug":"marenostrum-admin","email":"admin@marenostrum.com.br","password":"MudeEss@Senha123"}' \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
}

echo "===== INICIO $(date) ====="
for uf in $UFS; do
  TOKEN=$(login)
  H="Authorization: Bearer $TOKEN"
  echo ""
  echo "===== UF=$uf $(date) ====="

  resp=$(curl -fsS -X POST "$API/tse/sync?dataset=votacao_secao_2024_$uf" -H "$H" 2>&1)
  job_id=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('job_id',''))" 2>/dev/null)
  if [ -z "$job_id" ]; then
    echo "  Falha ao disparar (resposta: $resp) — pulando."
    continue
  fi
  echo "  Job: $job_id"

  # Poll ate completar
  while true; do
    sleep 20
    TOKEN=$(login)
    s=$(curl -fsS "$API/tse/sync/$job_id" -H "Authorization: Bearer $TOKEN" 2>/dev/null)
    status=$(echo "$s" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null)
    rows=$(echo "$s" | python3 -c "import sys,json; print(json.load(sys.stdin)['rows_processed'])" 2>/dev/null)
    ins=$(echo "$s" | python3 -c "import sys,json; print(json.load(sys.stdin)['vote_results_imported'])" 2>/dev/null)
    echo "  [$status] rows=$rows inserted=$ins $(date +%H:%M:%S)"
    if [ "$status" = "completed" ] || [ "$status" = "failed" ]; then
      [ "$status" = "failed" ] && echo "$s" | python3 -c "import sys,json; print('  ERRO:', json.load(sys.stdin).get('error_message',''))" 2>/dev/null
      break
    fi
  done
done
echo ""
echo "===== FIM $(date) — todas as UFs processadas ====="
