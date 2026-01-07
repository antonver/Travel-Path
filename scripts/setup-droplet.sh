#!/bin/bash
# =================================================================
# TravelPath Backend - DigitalOcean Droplet Setup Script
# =================================================================
# Run this script on a fresh Ubuntu droplet to set up the backend
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
if ! command -v docker-compose &> /dev/null; then
    apt install -y docker-compose-plugin
    echo "Docker Compose installed successfully"
else
    echo "Docker Compose already installed"
fi

# Install Git
echo "📥 Installing Git..."
apt install -y git

# Create app directory
echo "📁 Creating app directory..."
mkdir -p ~/travelpath-backend
cd ~/travelpath-backend

# Clone repository (if not exists)
if [ ! -d ".git" ]; then
    echo "📥 Cloning repository..."
    echo "Please enter your GitHub repository URL:"
    read REPO_URL
    git clone -b digitalocean $REPO_URL .
else
    echo "Repository already exists, pulling latest..."
    git fetch origin digitalocean
    git reset --hard origin/digitalocean
fi

# Create .env file
echo "⚙️ Creating .env file..."
if [ ! -f ".env" ]; then
    cat > .env << 'EOF'
# TravelPath Backend Environment Variables
# Fill in your values below

# Google Maps API Key (required)
MAPS_API_KEY=your_google_maps_api_key

# MinIO credentials
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=your_secure_password_here

# Base URL (your droplet IP or domain)
BASE_URL=http://YOUR_DROPLET_IP:8000

# Weather API (optional)
WEATHER_API_KEY=
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
ufw allow 9000/tcp  # MinIO API (optional)
ufw allow 9001/tcp  # MinIO Console (optional)
ufw --force enable

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env file: nano ~/travelpath-backend/.env"
echo "2. Copy Firebase credentials: scp serviceAccountKey.json root@IP:~/travelpath-backend/"
echo "3. Start the server: cd ~/travelpath-backend && docker compose -f docker-compose.prod.yml up -d"
echo ""
echo "Your services will be available at:"
echo "  - REST API: http://YOUR_IP:8000"
echo "  - gRPC: YOUR_IP:50051"
echo "  - MinIO Console: http://YOUR_IP:9001"
echo ""

