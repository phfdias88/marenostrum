#!/usr/bin/env bash
# ----------------------------------------------------------------------------
# Deploy-hook do certbot: recarrega o nginx DOCKERIZADO depois que o certificado
# e' renovado. Sem isto, o certbot do HOST renova os arquivos em /etc/letsencrypt
# (montado :ro no container), mas o nginx dentro do container continua servindo
# o cert ANTIGO em memoria ate' o proximo restart — resultando em cert expirado
# no ar a cada ~90 dias, sem ninguem perceber.
#
# COMO REGISTRAR (uma vez, no HOST, como root — escolha UMA opcao):
#
#   A) Hook global de renovacao (roda em TODA renovacao bem-sucedida):
#      sudo ln -s /home/deploy/marenostrum/scripts/certbot-deploy-hook.sh \
#                 /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
#      sudo chmod +x /home/deploy/marenostrum/scripts/certbot-deploy-hook.sh
#
#   B) Direto no comando de renovacao / no timer do certbot:
#      certbot renew --deploy-hook /home/deploy/marenostrum/scripts/certbot-deploy-hook.sh
#
# Testar sem esperar 90 dias:
#   sudo certbot renew --dry-run   (nao dispara deploy-hook)
#   sudo /home/deploy/marenostrum/scripts/certbot-deploy-hook.sh   (roda o hook direto)
# ----------------------------------------------------------------------------
set -uo pipefail

COMPOSE_DIR=/home/deploy/marenostrum
cd "$COMPOSE_DIR" || { echo "$(date -Is) ERRO: $COMPOSE_DIR nao encontrado" >&2; exit 0; }

# Valida a config ANTES de recarregar — um reload com config quebrada nao pode
# derrubar o proxy que ja esta no ar.
if docker compose exec -T nginx nginx -t >/dev/null 2>&1; then
  if docker compose exec -T nginx nginx -s reload >/dev/null 2>&1; then
    echo "$(date -Is) nginx recarregado apos renovacao do certificado"
  else
    echo "$(date -Is) AVISO: 'nginx -s reload' falhou" >&2
  fi
else
  echo "$(date -Is) AVISO: 'nginx -t' falhou — reload abortado (config invalida)" >&2
fi
# Sempre sai 0: o hook nao deve fazer o certbot considerar a renovacao falha.
exit 0
