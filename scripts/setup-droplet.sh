#!/bin/bash
# =================================================================
# TravelPath Backend - DigitalOcean Droplet Setup Script
# =================================================================
# Run this script on a fresh Ubuntu droplet to set up the backend
# Uses Cloudflare R2 for object storage
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
    
    # Add current user to docker group
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

# Google Maps API Key (required)
MAPS_API_KEY=your_google_maps_api_key_here

# =================================================================
# Cloudflare R2 Object Storage
# =================================================================
# Get these from Cloudflare Dashboard > R2 > Manage R2 API Tokens

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

# Base URL - REPLACE with your droplet IP!
BASE_URL=http://YOUR_DROPLET_IP:8000
EOF
    
    echo ""
    echo "⚠️  IMPORTANT: Edit .env file with your actual values!"
    echo "    nano ~/travelpath-backend/.env"
    echo ""
else
    echo ".env file already exists"
fi

# Remind about Firebase credentials
echo ""
echo "⚠️  Don't forget to copy your Firebase credentials!"
echo "    scp serviceAccountKey.json root@YOUR_DROPLET_IP:~/travelpath-backend/"
echo ""

# Setup firewall
echo "🔥 Configuring firewall..."
ufw allow 22/tcp    # SSH
ufw allow 8000/tcp  # HTTP API
ufw allow 50051/tcp # gRPC
ufw --force enable

echo ""
echo "✅ Setup complete!"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "Next steps:"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "1. Edit .env file with your values:"
echo "   nano ~/travelpath-backend/.env"
echo ""
echo "2. Copy Firebase credentials from your local machine:"
echo "   scp serviceAccountKey.json root@$(curl -s ifconfig.me):~/travelpath-backend/"
echo ""
echo "3. Start the server:"
echo "   cd ~/travelpath-backend && docker compose -f docker-compose.prod.yml up -d"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "Your services will be available at:"
echo "  - REST API: http://$(curl -s ifconfig.me):8000"
echo "  - gRPC:     $(curl -s ifconfig.me):50051"
echo "  - Docs:     http://$(curl -s ifconfig.me):8000/docs"
echo "═══════════════════════════════════════════════════════════════"
echo ""
