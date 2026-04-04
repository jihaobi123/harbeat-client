#!/bin/bash
# HarBeat — Server Initial Setup Script
# Run on a fresh Ubuntu 22.04 ECS instance
# Usage: bash setup-server.sh

set -e

echo "========================================="
echo "  HarBeat Server Setup"
echo "========================================="

# 1. Update system
echo "[1/5] Updating system packages..."
apt-get update && apt-get upgrade -y

# 2. Install Docker
echo "[2/5] Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    echo "  Docker installed: $(docker --version)"
else
    echo "  Docker already installed: $(docker --version)"
fi

# 3. Install Docker Compose (included in modern Docker, but verify)
echo "[3/5] Verifying Docker Compose..."
docker compose version || {
    echo "Installing Docker Compose plugin..."
    apt-get install -y docker-compose-plugin
}

# 4. Install Git
echo "[4/5] Installing Git..."
apt-get install -y git

# 5. Clone project
echo "[5/5] Cloning HarBeat project..."
cd /opt
if [ -d "harbeat" ]; then
    echo "  Project directory exists, pulling latest..."
    cd harbeat
    git pull
else
    git clone https://github.com/jihaobi123/harbeat-client.git harbeat
    cd harbeat
fi

# 6. Setup .env
if [ ! -f .env ]; then
    cp deploy/.env.example .env
    # Generate a random JWT secret
    JWT_SECRET=$(openssl rand -hex 32)
    sed -i "s|JWT_SECRET=.*|JWT_SECRET=$JWT_SECRET|" .env
    echo ""
    echo "  .env created with random JWT_SECRET"
    echo "  Review it: nano /opt/harbeat/.env"
fi

# 7. Configure firewall (if ufw is active)
if command -v ufw &> /dev/null; then
    ufw allow 22/tcp   # SSH
    ufw allow 80/tcp   # HTTP
    ufw allow 443/tcp  # HTTPS
    echo "  Firewall ports opened: 22, 80, 443"
fi

echo ""
echo "========================================="
echo "  Setup complete!"
echo "========================================="
echo ""
echo "  Next steps:"
echo "  1. Review .env:        nano /opt/harbeat/.env"
echo "  2. Start services:     cd /opt/harbeat && docker compose up -d --build"
echo "  3. Check status:       docker compose ps"
echo "  4. View logs:          docker compose logs -f app"
echo ""
echo "  First build will take ~10 minutes (downloading torch, etc.)"
echo ""
