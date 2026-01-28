#!/bin/bash
# docker-test.sh - Quick validation script for Shadowpulse Docker setup

set -e

echo "🐳 Shadowpulse Docker Setup Validator"
echo "======================================"
echo ""

# Check Docker installation
echo "1️⃣  Checking Docker installation..."
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found. Please install Docker Desktop."
    exit 1
fi
docker --version
echo "✅ Docker installed"
echo ""

# Check Docker Compose
echo "2️⃣  Checking Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose not found. Please install Docker Compose."
    exit 1
fi
docker-compose --version
echo "✅ Docker Compose installed"
echo ""

# Check required files
echo "3️⃣  Checking required files..."
required_files=("Dockerfile" "docker-compose.yml" "requirements.txt" "config.py" "dashboard.py")
for file in "${required_files[@]}"; do
    if [ ! -f "$file" ]; then
        echo "❌ Missing file: $file"
        exit 1
    fi
    echo "   ✅ $file"
done
echo ""

# Check port availability
echo "4️⃣  Checking port availability..."
ports=(8501 9200 9050)
for port in "${ports[@]}"; do
    if nc -z localhost $port 2>/dev/null; then
        echo "⚠️  Port $port is already in use. This may conflict."
    else
        echo "   ✅ Port $port available"
    fi
done
echo ""

# Check config.py for environment variable support
echo "5️⃣  Verifying config.py has environment variable support..."
if grep -q "os.getenv" config.py; then
    echo "   ✅ config.py uses os.getenv (environment variables supported)"
else
    echo "❌ config.py doesn't use os.getenv. Please update config.py."
    exit 1
fi
echo ""

# Validate docker-compose.yml syntax
echo "6️⃣  Validating docker-compose.yml..."
if docker-compose config > /dev/null 2>&1; then
    echo "   ✅ docker-compose.yml syntax is valid"
else
    echo "❌ docker-compose.yml has syntax errors"
    docker-compose config
    exit 1
fi
echo ""

# Validate Dockerfile
echo "7️⃣  Validating Dockerfile..."
if [ -f "Dockerfile" ]; then
    echo "   ✅ Dockerfile present"
    if grep -q "python:3.10-slim" Dockerfile; then
        echo "   ✅ Uses python:3.10-slim (lightweight)"
    fi
    if grep -q "curl" Dockerfile; then
        echo "   ✅ Installs curl for health checks"
    fi
else
    echo "❌ Dockerfile not found"
    exit 1
fi
echo ""

echo "════════════════════════════════════════"
echo "✅ All checks passed! Ready to run Docker."
echo ""
echo "Next steps:"
echo "  1. Build: docker-compose build"
echo "  2. Start: docker-compose up"
echo "  3. Open:  http://localhost:8501"
echo ""
