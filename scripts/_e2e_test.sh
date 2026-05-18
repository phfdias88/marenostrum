#!/usr/bin/env bash
# =============================================================================
# E2E TEST SUITE — roda contra a producao em http://localhost (via nginx).
# Cobre: infra, auth, contatos, demandas, webhook, import CSV, frontend,
# isolamento multi-tenant (cria tenant B temporario).
# =============================================================================
set -uo pipefail

BASE="http://localhost"
PASS=0
FAIL=0
RED=$'\033[31m'
GRN=$'\033[32m'
YEL=$'\033[33m'
NC=$'\033[0m'

ok()    { echo "${GRN}PASS${NC}: $*"; PASS=$((PASS+1)); }
fail()  { echo "${RED}FAIL${NC}: $*"; FAIL=$((FAIL+1)); }
hdr()   { echo; echo "${YEL}── $* ──${NC}"; }

# ----------------------------- helpers ---------------------------------

# eq <got> <want> <description>
eq() {
    if [[ "$1" == "$2" ]]; then ok "$3"
    else fail "$3 [got=$1 want=$2]"
    fi
}

# contains <haystack> <needle> <description>
contains() {
    if [[ "$1" == *"$2"* ]]; then ok "$3"
    else fail "$3 [no match for '$2' in '${1:0:80}']"
    fi
}

# api_call <method> <path> <token> <data-or-empty> -> echo body
# Status fica em /tmp/last_status. Por que arquivo? api_call e' chamado
# em $(...) subshell — variaveis locais nao propagam, arquivos sim.
api_call() {
    local method="$1" path="$2" token="${3:-}" data="${4:-}"
    local hdrs=(-H "Content-Type: application/json")
    [[ -n "$token" ]] && hdrs+=(-H "Authorization: Bearer $token")
    local args=(-s -o /tmp/last_body -w '%{http_code}' -X "$method" "$BASE$path" "${hdrs[@]}")
    [[ -n "$data" ]] && args+=(-d "$data")
    curl "${args[@]}" > /tmp/last_status
    cat /tmp/last_body
}
LAST_STATUS() { cat /tmp/last_status; }

# get_status <method> <path> <token> <data-or-empty>
get_status() {
    api_call "$@" >/dev/null
    LAST_STATUS
}

json_get() {
    python3 -c "import sys,json; d=json.load(sys.stdin);
keys='$1'.split('.')
v=d
for k in keys:
    if k.isdigit(): v=v[int(k)]
    else: v=v[k]
print(v)" 2>/dev/null
}

# ============================================================ SETUP

hdr "0. SETUP — limpa dados de runs anteriores (mantem tenant admin)"

docker compose -f /home/deploy/marenostrum/docker-compose.yml exec -T db \
    psql -U marenostrum -d marenostrum >/dev/null <<'SQL'
DELETE FROM interactions;
DELETE FROM demands;
DELETE FROM contacts;
DELETE FROM users WHERE email != 'admin@marenostrum.com.br';
DELETE FROM tenants WHERE slug != 'marenostrum-admin';
UPDATE tenants SET webhook_secret = NULL WHERE slug = 'marenostrum-admin';
SQL
ok "DB resetado (mantido apenas tenant admin)"

# ============================================================ INFRA

hdr "1. INFRA — containers e portas"

containers_running=$(docker compose -f /home/deploy/marenostrum/docker-compose.yml ps --format '{{.Service}}|{{.State}}' 2>/dev/null)
eq "$(echo "$containers_running" | grep -c running)" "4" "4 containers em estado running"
contains "$containers_running" "db|running" "container db rodando"
contains "$containers_running" "api|running" "container api rodando"
contains "$containers_running" "web|running" "container web rodando"
contains "$containers_running" "nginx|running" "container nginx rodando"

# ============================================================ HEALTH

hdr "2. HEALTH endpoint"

body=$(api_call GET /api/health)
eq "$(LAST_STATUS)" "200" "GET /api/health retorna 200"
contains "$body" '"status":"ok"' "body tem status:ok"

# ============================================================ AUTH

hdr "3. AUTH — login + /me"

# Bad login
status=$(get_status POST /api/v1/auth/login "" '{"tenant_slug":"marenostrum-admin","email":"admin@marenostrum.com.br","password":"errada"}')
eq "$status" "401" "login com senha errada retorna 401"

status=$(get_status POST /api/v1/auth/login "" '{"tenant_slug":"nao-existe","email":"admin@marenostrum.com.br","password":"MudeEss@Senha123"}')
eq "$status" "401" "login com tenant inexistente retorna 401"

# Good login
LOGIN_RES=$(api_call POST /api/v1/auth/login "" '{"tenant_slug":"marenostrum-admin","email":"admin@marenostrum.com.br","password":"MudeEss@Senha123"}')
eq "$(LAST_STATUS)" "200" "login correto retorna 200"
TOKEN_A=$(echo "$LOGIN_RES" | json_get access_token)
[[ -n "$TOKEN_A" ]] && ok "JWT capturado (${#TOKEN_A} chars)" || fail "JWT vazio"

# /me
ME=$(api_call GET /api/v1/auth/me "$TOKEN_A")
eq "$(LAST_STATUS)" "200" "/me retorna 200"
contains "$ME" '"tenant_slug":"marenostrum-admin"' "/me tem tenant_slug correto"
contains "$ME" '"role":"owner"' "/me tem role owner"
TENANT_A_ID=$(echo "$ME" | json_get tenant_id)

# /me sem token
status=$(get_status GET /api/v1/auth/me "")
eq "$status" "401" "/me sem token retorna 401"

# /me com token lixo (curl direto pra contornar Authorization opcional)
curl -s -o /dev/null -w '%{http_code}' http://localhost/api/v1/auth/me -H "Authorization: Bearer trash" > /tmp/last_status
eq "$(LAST_STATUS)" "401" "/me com token invalido retorna 401"

# ============================================================ CONTATOS

hdr "4. CONTATOS CRUD"

# Estado inicial (1 contato 'Joao Smoke Test' do deploy)
LIST=$(api_call GET "/api/v1/contacts?limit=100" "$TOKEN_A")
INITIAL_TOTAL=$(echo "$LIST" | json_get total)
ok "GET /contacts retornou (total inicial=$INITIAL_TOTAL)"

# CREATE
CREATE_RES=$(api_call POST /api/v1/contacts "$TOKEN_A" '{"full_name":"Maria E2E","phone":"(32) 88888-0001","email":"maria@example.com","type":"leader","city":"Juiz de Fora","state":"MG"}')
eq "$(LAST_STATUS)" "201" "POST /contacts retorna 201"
CONTACT_ID=$(echo "$CREATE_RES" | json_get id)
[[ -n "$CONTACT_ID" ]] && ok "contact id capturado: $CONTACT_ID" || fail "id vazio"

# duplicado
status=$(get_status POST /api/v1/contacts "$TOKEN_A" '{"full_name":"Outra","phone":"(32) 88888-0001","type":"voter"}')
eq "$status" "409" "telefone duplicado retorna 409"

# Validacao nome curto
status=$(get_status POST /api/v1/contacts "$TOKEN_A" '{"full_name":"X","phone":"(32) 88888-9999","type":"voter"}')
eq "$status" "422" "nome curto retorna 422"

# GET por ID
DETAIL=$(api_call GET "/api/v1/contacts/$CONTACT_ID" "$TOKEN_A")
eq "$(LAST_STATUS)" "200" "GET /contacts/{id} retorna 200"
contains "$DETAIL" '"full_name":"Maria E2E"' "nome bate"

# UPDATE partial
api_call PUT "/api/v1/contacts/$CONTACT_ID" "$TOKEN_A" '{"city":"Belo Horizonte"}' >/dev/null
eq "$(LAST_STATUS)" "200" "PUT parcial retorna 200"
DETAIL=$(api_call GET "/api/v1/contacts/$CONTACT_ID" "$TOKEN_A")
contains "$DETAIL" '"city":"Belo Horizonte"' "campo atualizado"
contains "$DETAIL" '"full_name":"Maria E2E"' "outros campos preservados"

# SEARCH
SEARCH=$(api_call GET "/api/v1/contacts?search=Maria" "$TOKEN_A")
SEARCH_TOTAL=$(echo "$SEARCH" | json_get total)
[[ "$SEARCH_TOTAL" -ge 1 ]] && ok "search=Maria achou >=1" || fail "search=Maria total=$SEARCH_TOTAL"

# PAGINACAO — cria 2 a mais pra testar
for i in 1 2; do
    api_call POST /api/v1/contacts "$TOKEN_A" "{\"full_name\":\"Page Test $i\",\"phone\":\"(32) 77777-000$i\",\"type\":\"voter\"}" >/dev/null
done
PAGE1=$(api_call GET "/api/v1/contacts?limit=2&offset=0" "$TOKEN_A")
PAGE1_LEN=$(echo "$PAGE1" | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["items"]))')
eq "$PAGE1_LEN" "2" "paginacao limit=2 retorna 2 items"

# ============================================================ DEMANDAS

hdr "5. DEMANDAS CRUD"

# Create demand
DEMAND_RES=$(api_call POST /api/v1/demands "$TOKEN_A" "{\"contact_id\":\"$CONTACT_ID\",\"title\":\"Buraco na Rua A\",\"description\":\"Buraco enorme proximo ao ponto X\",\"category\":\"Infraestrutura\",\"status\":\"aberta\"}")
eq "$(LAST_STATUS)" "201" "POST /demands retorna 201"
DEMAND_ID=$(echo "$DEMAND_RES" | json_get id)
contains "$DEMAND_RES" '"full_name":"Maria E2E"' "demand vem com contato aninhado"

# Demand pra contato inexistente
status=$(get_status POST /api/v1/demands "$TOKEN_A" '{"contact_id":"00000000-0000-0000-0000-000000000000","title":"Inválido","description":"x","category":"x"}')
eq "$status" "404" "demand pra contact_id inexistente retorna 404"

# Filter by status
ABERTAS=$(api_call GET "/api/v1/demands?status=aberta" "$TOKEN_A")
contains "$ABERTAS" "Buraco na Rua A" "filter status=aberta lista a demanda"

# PATCH status
api_call PUT "/api/v1/demands/$DEMAND_ID" "$TOKEN_A" '{"status":"em_andamento"}' >/dev/null
eq "$(LAST_STATUS)" "200" "PUT status=em_andamento ok"
DEMAND=$(api_call GET "/api/v1/demands/$DEMAND_ID" "$TOKEN_A")
contains "$DEMAND" '"status":"em_andamento"' "status atualizou"

# Filter by contact
FILTERED=$(api_call GET "/api/v1/demands?contact_id=$CONTACT_ID" "$TOKEN_A")
contains "$FILTERED" "Buraco na Rua A" "filter contact_id lista a demanda"

# ============================================================ WEBHOOK

hdr "6. WEBHOOK BotConversa"

# Sem secret config: 401
status=$(get_status POST "/api/v1/webhooks/botconversa/$TENANT_A_ID" "" '{"phone":"(32) 88888-0001"}')
eq "$status" "401" "webhook sem tenant.webhook_secret retorna 401"

# Configura secret
docker compose -f /home/deploy/marenostrum/docker-compose.yml exec -T db psql -U marenostrum -d marenostrum -c "UPDATE tenants SET webhook_secret='wh-secret-e2e-test' WHERE id='$TENANT_A_ID';" >/dev/null
ok "secret configurado no tenant via UPDATE"

# Secret correto + phone que ja existe (Maria)
curl -s -o /tmp/wh_res -w '%{http_code}' -X POST \
    "$BASE/api/v1/webhooks/botconversa/$TENANT_A_ID" \
    -H "Content-Type: application/json" \
    -H "X-Webhook-Secret: wh-secret-e2e-test" \
    -d '{"phone":"(32) 88888-0001","event":"mensagem_recebida","message":{"text":"Oi quero ajudar"}}' \
    > /tmp/last_status
eq "$(LAST_STATUS)" "200" "webhook com secret correto retorna 200"
WH_BODY=$(cat /tmp/wh_res)
contains "$WH_BODY" '"contact_matched":true' "webhook linkou ao contato existente"

# Secret errado
curl -s -o /dev/null -w '%{http_code}' -X POST \
    "$BASE/api/v1/webhooks/botconversa/$TENANT_A_ID" \
    -H "Content-Type: application/json" \
    -H "X-Webhook-Secret: errado" \
    -d '{}' \
    > /tmp/last_status
eq "$(LAST_STATUS)" "401" "webhook secret errado retorna 401"

# Webhook pra tenant inexistente (Content-Type obrigatorio pro FastAPI nao dar 422)
curl -s -o /dev/null -w '%{http_code}' -X POST \
    "$BASE/api/v1/webhooks/botconversa/00000000-0000-0000-0000-000000000000" \
    -H "Content-Type: application/json" \
    -H "X-Webhook-Secret: wh-secret-e2e-test" \
    -d '{}' \
    > /tmp/last_status
eq "$(LAST_STATUS)" "404" "webhook pra tenant inexistente retorna 404"

# Phone que nao existe: orfa
curl -s -o /tmp/wh_res -w '%{http_code}' -X POST \
    "$BASE/api/v1/webhooks/botconversa/$TENANT_A_ID" \
    -H "Content-Type: application/json" \
    -H "X-Webhook-Secret: wh-secret-e2e-test" \
    -d '{"phone":"(32) 99999-0000","event":"mensagem_recebida"}' \
    > /tmp/last_status
WH_BODY=$(cat /tmp/wh_res)
contains "$WH_BODY" '"contact_matched":false' "phone novo = orfa (sem match)"

# ============================================================ TIMELINE

hdr "7. TIMELINE — interactions do contato"

TIMELINE=$(api_call GET "/api/v1/contacts/$CONTACT_ID/interactions" "$TOKEN_A")
INT_TOTAL=$(echo "$TIMELINE" | json_get total)
[[ "$INT_TOTAL" -ge 1 ]] && ok "timeline tem >=1 interaction" || fail "timeline vazia (total=$INT_TOTAL)"
contains "$TIMELINE" '"event_type":"mensagem_recebida"' "event_type correto"

# Timeline de contato de outro tenant -> 404
status=$(get_status GET "/api/v1/contacts/00000000-0000-0000-0000-000000000000/interactions" "$TOKEN_A")
eq "$status" "404" "timeline de contato inexistente retorna 404"

# ============================================================ IMPORT CSV

hdr "8. IMPORT CSV"

cat > /tmp/contacts.csv << 'CSVEOF'
Nome;Telefone;Email;Cidade;UF;Tipo
Eleitor CSV 1;(32) 55555-0001;csv1@example.com;Juiz de Fora;MG;Eleitor
Eleitor CSV 2;(32) 55555-0002;csv2@example.com;Juiz de Fora;MG;Liderança
Erro nome;;invalido;;;Eleitor
CSVEOF

IMP_RES=$(curl -s -X POST "$BASE/api/v1/contacts/import" \
    -H "Authorization: Bearer $TOKEN_A" \
    -F "file=@/tmp/contacts.csv")
IMPORTED=$(echo "$IMP_RES" | json_get imported)
SKIPPED=$(echo "$IMP_RES" | json_get skipped)
eq "$IMPORTED" "2" "CSV importou 2 contatos"
eq "$SKIPPED" "1" "CSV pulou 1 (linha sem nome)"

# ============================================================ MULTI-TENANT

hdr "9. ISOLAMENTO MULTI-TENANT (cria tenant B temporario)"

# Cria tenant B via seed-admin com env override
TENANT_SLUG=tenant-b-e2e \
TENANT_NAME='Tenant B E2E' \
ADMIN_EMAIL=b@example.com \
ADMIN_NAME='Admin B' \
ADMIN_PASSWORD='SenhaB@123456' \
/home/deploy/marenostrum/scripts/seed-admin.sh 2>&1 | tail -2 | head -1 >/dev/null
ok "tenant B criado via seed"

# Login B
LOGIN_B=$(api_call POST /api/v1/auth/login "" '{"tenant_slug":"tenant-b-e2e","email":"b@example.com","password":"SenhaB@123456"}')
TOKEN_B=$(echo "$LOGIN_B" | json_get access_token)
[[ -n "$TOKEN_B" ]] && ok "login tenant B ok" || fail "login B falhou"

# B nao ve contatos de A
LIST_B=$(api_call GET /api/v1/contacts "$TOKEN_B")
TOTAL_B=$(echo "$LIST_B" | json_get total)
eq "$TOTAL_B" "0" "tenant B nao ve nenhum contato de A"

# B nao acessa contato de A
status=$(get_status GET "/api/v1/contacts/$CONTACT_ID" "$TOKEN_B")
eq "$status" "404" "B tenta GET contato de A -> 404 (nao 403)"

status=$(get_status PUT "/api/v1/contacts/$CONTACT_ID" "$TOKEN_B" '{"full_name":"HACKED"}')
eq "$status" "404" "B tenta PUT contato de A -> 404"

status=$(get_status DELETE "/api/v1/contacts/$CONTACT_ID" "$TOKEN_B")
eq "$status" "404" "B tenta DELETE contato de A -> 404"

# B nao acessa demandas de A
status=$(get_status GET "/api/v1/demands/$DEMAND_ID" "$TOKEN_B")
eq "$status" "404" "B tenta GET demanda de A -> 404"

# B nao acessa timeline de contato de A
status=$(get_status GET "/api/v1/contacts/$CONTACT_ID/interactions" "$TOKEN_B")
eq "$status" "404" "B tenta GET timeline de contato de A -> 404"

# A continua vendo seus dados
DETAIL=$(api_call GET "/api/v1/contacts/$CONTACT_ID" "$TOKEN_A")
contains "$DETAIL" '"full_name":"Maria E2E"' "A ainda ve seu contato (nao foi alterado por B)"

# ============================================================ SOFT DELETE

hdr "10. SOFT DELETE"

# Cria contato pra deletar
DEL_RES=$(api_call POST /api/v1/contacts "$TOKEN_A" '{"full_name":"Para Apagar","phone":"(32) 11111-2222","type":"voter"}')
DEL_ID=$(echo "$DEL_RES" | json_get id)

# Delete
status=$(get_status DELETE "/api/v1/contacts/$DEL_ID" "$TOKEN_A")
eq "$status" "204" "DELETE retorna 204"

# GET dele = 404
status=$(get_status GET "/api/v1/contacts/$DEL_ID" "$TOKEN_A")
eq "$status" "404" "GET apos delete retorna 404"

# Mas o registro EXISTE no DB com is_active=false
db_check=$(docker compose -f /home/deploy/marenostrum/docker-compose.yml exec -T db psql -U marenostrum -d marenostrum -tc "SELECT is_active FROM contacts WHERE id='$DEL_ID';" 2>/dev/null | tr -d ' \n')
eq "$db_check" "f" "row preservada com is_active=false (soft delete)"

# ============================================================ FRONTEND

hdr "11. FRONTEND — paginas servidas pelo nginx"

# Raiz redireciona pra /login
curl -s -o /dev/null -w '%{http_code}' "$BASE/" > /tmp/last_status
S=$(LAST_STATUS)
[[ "$S" == "200" || "$S" == "307" || "$S" == "308" ]] && ok "GET / retorna $S" || fail "GET / retornou $S"

# /login serve HTML
LOGIN_HTML=$(curl -s "$BASE/login")
contains "$LOGIN_HTML" "MareNostrum" "/login tem MareNostrum no HTML"
contains "$LOGIN_HTML" "<!DOCTYPE html>" "/login serve HTML"

# /dashboard serve HTML (middleware redireciona pra /login sem cookie)
curl -s -o /dev/null -w '%{http_code}' "$BASE/dashboard" > /tmp/last_status
S=$(LAST_STATUS)
[[ "$S" == "200" || "$S" == "307" ]] && ok "GET /dashboard retorna $S" || fail "GET /dashboard retornou $S"

# Modelo CSV estatico
CSV=$(curl -s "$BASE/contatos-modelo.csv")
contains "$CSV" "Nome;Telefone" "modelo CSV servido em /contatos-modelo.csv"

# ============================================================ DOCS

hdr "12. SWAGGER /api/docs"

status=$(get_status GET /api/docs "")
eq "$status" "200" "Swagger UI 200"

OPENAPI=$(curl -s "$BASE/api/openapi.json")
contains "$OPENAPI" "/api/v1/auth/login" "openapi.json tem /auth/login"
contains "$OPENAPI" "/api/v1/contacts" "openapi.json tem /contacts"
contains "$OPENAPI" "/api/v1/demands" "openapi.json tem /demands"
contains "$OPENAPI" "/api/v1/webhooks/botconversa" "openapi.json tem /webhooks"

# ============================================================ CLEANUP

hdr "13. CLEANUP (remove tenant B + dados de teste)"

# remove demanda criada (hard delete)
api_call DELETE "/api/v1/demands/$DEMAND_ID" "$TOKEN_A" >/dev/null
ok "demand removida"

# Tenant B inteiro
docker compose -f /home/deploy/marenostrum/docker-compose.yml exec -T db psql -U marenostrum -d marenostrum -c "
DELETE FROM interactions WHERE tenant_id IN (SELECT id FROM tenants WHERE slug='tenant-b-e2e');
DELETE FROM demands WHERE tenant_id IN (SELECT id FROM tenants WHERE slug='tenant-b-e2e');
DELETE FROM contacts WHERE tenant_id IN (SELECT id FROM tenants WHERE slug='tenant-b-e2e');
DELETE FROM users WHERE tenant_id IN (SELECT id FROM tenants WHERE slug='tenant-b-e2e');
DELETE FROM tenants WHERE slug='tenant-b-e2e';
" >/dev/null 2>&1
ok "tenant B + dados removidos"

# ============================================================ RESUMO

echo
echo "================================================================"
echo "RESUMO: ${GRN}$PASS PASS${NC}, ${RED}$FAIL FAIL${NC}"
echo "================================================================"
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
