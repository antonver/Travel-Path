#!/bin/bash
# =================================================================
# TravelPath Backend - DigitalOcean Droplet Setup Script
# =================================================================
# Run this script on a fresh Ubuntu droplet to set up the backend
# Uses Cloudflare R2 for object storage
# Caddy for automatic HTTPS
# 
# Usage: 
#   chmod +x setup-droplet.sh
#   ./setup-droplet.sh
# =================================================================

set -e

echo "🚀 Setting up TravelPath Backend on DigitalOcean..."

# Update system
echo "📦 Updating system packages..."
apt update && apt upgrade -y

# Install Docker
echo "🐳 Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
    usermod -aG docker $USER
    echo "Docker installed successfully"
else
    echo "Docker already installed"
fi

# Install Docker Compose
echo "🐳 Installing Docker Compose..."
apt install -y docker-compose-plugin

# Install Git and curl
echo "📥 Installing Git..."
apt install -y git curl

# Create app directory
echo "📁 Creating app directory..."
mkdir -p ~/travelpath-backend
cd ~/travelpath-backend

# Clone repository (if not exists)
if [ ! -d ".git" ]; then
    echo "📥 Cloning repository..."
    git clone -b digitalocean https://github.com/antonver/Travel-Path.git .
else
    echo "Repository already exists, pulling latest..."
    git fetch origin digitalocean
    git reset --hard origin/digitalocean
fi

# Create .env file
echo "⚙️ Creating .env file..."
if [ ! -f ".env" ]; then
    cat > .env << 'EOF'
# =================================================================
# TravelPath Backend - Environment Variables
# =================================================================

# Your domain (for HTTPS) - REQUIRED!
# Example: api.yourdomain.com
DOMAIN=YOUR_DOMAIN_HERE

# Google Maps API Key (required)
MAPS_API_KEY=your_google_maps_api_key_here

# =================================================================
# Cloudflare R2 Object Storage
# =================================================================

# R2 Endpoint (format: <account_id>.r2.cloudflarestorage.com)
R2_ENDPOINT=your_account_id.r2.cloudflarestorage.com

# R2 Access Key ID  
R2_ACCESS_KEY_ID=your_access_key_id

# R2 Secret Access Key
R2_SECRET_ACCESS_KEY=your_secret_access_key

# R2 Bucket Name
R2_BUCKET_NAME=travel-photos

# =================================================================
# Server Configuration
# =================================================================

# Base URL - use HTTPS with your domain!
# Example: https://api.yourdomain.com
BASE_URL=https://YOUR_DOMAIN_HERE
EOF
    
    echo ""
    echo "⚠️  IMPORTANT: Edit .env file with your actual values!"
    echo "    nano ~/travelpath-backend/.env"
    echo ""
else
    echo ".env file already exists"
fi

# Setup firewall
echo "🔥 Configuring firewall..."
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP (for Let's Encrypt challenge)
ufw allow 443/tcp   # HTTPS
ufw allow 50051/tcp # gRPC
ufw --force enable

echo ""
echo "✅ Setup complete!"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "ВАЖНО: Перед запуском сервера"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "1. Настрой DNS для твоего домена:"
echo "   Добавь A-запись: api.yourdomain.com → $(curl -s ifconfig.me)"
echo ""
echo "2. Редактируй .env файл:"
echo "   nano ~/travelpath-backend/.env"
echo ""
echo "3. Скопируй Firebase credentials:"
echo "   scp serviceAccountKey.json root@$(curl -s ifconfig.me):~/travelpath-backend/"
echo ""
echo "4. Запусти сервер:"
echo "   cd ~/travelpath-backend && docker compose -f docker-compose.prod.yml up -d"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "После запуска твои сервисы будут на:"
echo "  - REST API: https://YOUR_DOMAIN (автоматический HTTPS!)"
echo "  - gRPC:     $(curl -s ifconfig.me):50051"
echo "  - Docs:     https://YOUR_DOMAIN/docs"
echo "═══════════════════════════════════════════════════════════════"
echo ""
