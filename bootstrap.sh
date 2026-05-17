#!/bin/bash
# ArimaRun Control Plane Bootstrap Script
# Run this script as root on your fresh Ubuntu VPS: sudo bash bootstrap.sh

set -e

echo "🚀 Starting ArimaRun VPS Bootstrap..."

# 1. System Update
echo "🔄 Updating system packages..."
apt-get update && apt-get upgrade -y
apt-get install -y ca-certificates curl gnupg ufw git

# 2. Security Hardening (UFW Firewall)
echo "🛡️ Configuring UFW Firewall..."
ufw default deny incoming
ufw default allow outgoing
# Allow SSH (Port 22)
ufw allow ssh
# Allow HTTP/HTTPS (Ports 80 and 443) for Traefik
ufw allow http
ufw allow https
# Enable UFW without prompting
ufw --force enable

# 3. Install Docker & Docker Compose
echo "🐳 Installing Docker Engine..."
if ! command -v docker &> /dev/null; then
    # Add Docker's official GPG key:
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    # Set up the repository:
    echo \
      "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
else
    echo "✅ Docker already installed."
fi

# 4. Enable Docker to start on boot
systemctl enable docker
systemctl start docker

# 5. Prepare Traefik ACME directory
echo "🔐 Setting up Let's Encrypt Traefik storage..."
mkdir -p /root/arimarun/traefik
touch /root/arimarun/traefik/acme.json
chmod 600 /root/arimarun/traefik/acme.json

echo "==========================================================="
echo "🎉 VPS Bootstrap Complete!"
echo "Docker is installed and the firewall is strictly secured."
echo ""
echo "Next Steps:"
echo "1. Upload your arimarun-backend code to the VPS (e.g., into /root/arimarun/)."
echo "2. Navigate to your code folder: cd /root/arimarun/"
echo "3. Ensure your .env file is created with your Supabase details."
echo "4. Run your stack: docker compose -f docker-supabase.yml up -d --build"
echo "==========================================================="
