#!/usr/bin/env bash
# =============================================================================
# Setup INICIAL da VPS Hostinger (rode como ROOT, UMA UNICA vez via SSH).
# Cria usuario deploy, configura firewall, swap e libera Docker.
# =============================================================================
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "ERRO: rode como root (ssh root@72.60.248.41 + bash setup-vps.sh)"
    exit 1
fi

DEPLOY_USER="deploy"

echo "==> [1/6] Atualizando sistema..."
apt-get update && apt-get -y upgrade

echo "==> [2/6] Criando usuario '$DEPLOY_USER'..."
if ! id "$DEPLOY_USER" &>/dev/null; then
    adduser --disabled-password --gecos "" "$DEPLOY_USER"
    echo "Defina senha para $DEPLOY_USER:"
    passwd "$DEPLOY_USER"
fi
usermod -aG sudo,docker "$DEPLOY_USER" 2>/dev/null || usermod -aG sudo "$DEPLOY_USER"

echo "==> [3/6] Copiando chave SSH do root para o deploy (se houver)..."
if [[ -f /root/.ssh/authorized_keys ]]; then
    mkdir -p /home/$DEPLOY_USER/.ssh
    cp /root/.ssh/authorized_keys /home/$DEPLOY_USER/.ssh/authorized_keys
    chown -R $DEPLOY_USER:$DEPLOY_USER /home/$DEPLOY_USER/.ssh
    chmod 700 /home/$DEPLOY_USER/.ssh
    chmod 600 /home/$DEPLOY_USER/.ssh/authorized_keys
fi

echo "==> [4/6] Firewall (UFW)..."
apt-get install -y ufw
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> [5/6] Swap de 2GB (rede de seguranca contra OOM)..."
if [[ ! -f /swapfile ]]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    # swappiness baixo: so usa swap em ultimo caso
    sysctl vm.swappiness=10
    echo 'vm.swappiness=10' >> /etc/sysctl.conf
fi

echo "==> [6/6] Confirmando Docker..."
docker --version || { echo "ATENCAO: instale Docker manualmente (curl -fsSL https://get.docker.com | sh)"; }
docker compose version || echo "ATENCAO: Docker Compose v2 ausente"

echo ""
echo "OK. Proximos passos:"
echo "  1) Saia (exit) e reconecte como deploy:  ssh deploy@72.60.248.41"
echo "  2) Clone/envie o projeto para ~/marenostrum"
echo "  3) cp backend/.env.example backend/.env  (e edite!)"
echo "  4) ./scripts/deploy.sh"
