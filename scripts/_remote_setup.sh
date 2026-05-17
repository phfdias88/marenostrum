#!/usr/bin/env bash
# Setup automatizado da VPS — versao non-interactive do setup-vps.sh.
# Idempotente: pode rodar varias vezes.
set -euo pipefail

DEPLOY_USER="deploy"

echo "==> [1/5] Update do APT (non-interactive)..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ufw rsync git

echo "==> [2/5] Usuario '$DEPLOY_USER'..."
if ! id "$DEPLOY_USER" &>/dev/null; then
    # Senha randomica forte (deploy nunca vai logar via senha — so SSH key)
    adduser --disabled-password --gecos "" "$DEPLOY_USER"
fi
# Adiciona aos grupos sudo e docker
usermod -aG sudo,docker "$DEPLOY_USER" 2>/dev/null || usermod -aG sudo "$DEPLOY_USER"
# Sudo sem senha (pra deploy automatizado funcionar)
echo "$DEPLOY_USER ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/deploy
chmod 440 /etc/sudoers.d/deploy

echo "==> [3/5] Chave SSH no deploy (copia da do root)..."
if [[ -f /root/.ssh/authorized_keys ]]; then
    mkdir -p "/home/$DEPLOY_USER/.ssh"
    cp /root/.ssh/authorized_keys "/home/$DEPLOY_USER/.ssh/authorized_keys"
    chown -R "$DEPLOY_USER:$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
    chmod 700 "/home/$DEPLOY_USER/.ssh"
    chmod 600 "/home/$DEPLOY_USER/.ssh/authorized_keys"
fi

echo "==> [4/5] Firewall UFW..."
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> [5/5] Swap 2GB (rede de seguranca anti-OOM)..."
if [[ ! -f /swapfile ]]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    sysctl -q vm.swappiness=10
    grep -q 'vm.swappiness' /etc/sysctl.conf || echo 'vm.swappiness=10' >> /etc/sysctl.conf
fi

echo ""
echo "OK setup concluido. Estado:"
echo "  - Usuario deploy: criado, no grupo docker, sudo sem senha"
echo "  - Firewall: portas 22, 80, 443 abertas"
echo "  - Swap: $(free -m | grep Swap | awk '{print $2}')MB"
echo "  - Docker: $(docker --version)"
