#!/bin/bash
# Quick start script for Travel Path Backend

set -e

echo "=================================================="
echo "  Travel Path Backend - Quick Start"
echo "=================================================="
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo "Creating .env from .env.example..."
    
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✅ Created .env file"
        echo ""
        echo "⚠️  IMPORTANT: Edit .env and set your:"
        echo "   - MAPS_API_KEY"
        echo "   - Other configuration as needed"
        echo ""
        read -p "Press Enter after you've configured .env..."
    else
        echo "❌ .env.example not found!"
        exit 1
    fi
fi

# Check if serviceAccountKey.json exists
if [ ! -f serviceAccountKey.json ]; then
    echo "❌ serviceAccountKey.json not found!"
    echo ""
    echo "Please:"
    echo "1. Go to Firebase Console → Project Settings → Service Accounts"
    echo "2. Generate new private key"
    echo "3. Save it as 'serviceAccountKey.json' in this directory"
    echo ""
    exit 1
fi

echo "✅ Configuration files found"
echo ""

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed!"
    echo "Please install Docker Desktop from: https://www.docker.com/products/docker-desktop"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed!"
    exit 1
fi

echo "✅ Docker is installed"
echo ""

# Stop any existing containers
echo "🔍 Checking for existing containers..."
docker-compose down 2>/dev/null || true

# Build and start services
echo ""
echo "🚀 Building and starting services..."
echo ""
docker-compose up --build -d

echo ""
echo "⏳ Waiting for services to be ready..."
sleep 5

# Check if services are running
if docker-compose ps | grep -q "Up"; then
    echo ""
    echo "=================================================="
    echo "  ✅ Travel Path Backend is running!"
    echo "=================================================="
    echo ""
    echo "📡 Services:"
    echo "   • API Documentation: http://localhost:8000/docs"
    echo "   • ReDoc:            http://localhost:8000/redoc"
    echo "   • Health Check:     http://localhost:8000/health"
    echo "   • MinIO Console:    http://localhost:9001"
    echo ""
    echo "📋 Useful commands:"
    echo "   • View logs:        docker-compose logs -f"
    echo "   • View backend:     docker-compose logs -f backend"
    echo "   • Stop services:    docker-compose down"
    echo "   • Restart:          docker-compose restart"
    echo ""
    echo "🔧 MinIO Console Login:"
    echo "   Username: minioadmin"
    echo "   Password: minioadmin123"
    echo "   (or check your .env file for custom credentials)"
    echo ""
else
    echo ""
    echo "❌ Failed to start services"
    echo "Check logs with: docker-compose logs"
    exit 1
fi

