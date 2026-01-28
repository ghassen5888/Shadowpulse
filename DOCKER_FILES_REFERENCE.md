# Docker Files - Complete Reference

This document contains the exact content of all Docker-related files created for Shadowpulse.

## File 1: Dockerfile

Location: `/home/kali/shadowpulse/Dockerfile`

```dockerfile
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install only essential runtime dependencies (curl for health checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
# All packages in requirements.txt use pre-compiled wheels, so no build tools needed
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create a non-root user for security
RUN useradd -m -u 1000 shadowuser && chown -R shadowuser:shadowuser /app
USER shadowuser

# Expose Streamlit port
EXPOSE 8501

# Health check to verify app is running
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Run the Streamlit app
CMD ["streamlit", "run", "dashboard.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

---

## File 2: docker-compose.yml

Location: `/home/kali/shadowpulse/docker-compose.yml`

```yaml
version: '3.8'

services:
  # Elasticsearch single-node cluster with security disabled
  elasticsearch:
    image: elasticsearch:8.13.2
    container_name: shadowpulse-elasticsearch
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - ES_JAVA_OPTS=-Xms512m -Xmx512m
    ports:
      - "9200:9200"
    volumes:
      - elasticsearch_data:/usr/share/elasticsearch/data
    networks:
      - shadowpulse-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9200"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

  # Tor SOCKS proxy
  tor:
    image: peterdavehello/tor-socks-proxy:latest
    container_name: shadowpulse-tor
    ports:
      - "9050:9050"
    networks:
      - shadowpulse-network
    healthcheck:
      test: ["CMD", "curl", "-f", "-x", "socks5://127.0.0.1:9050", "http://ipv4.icanhazip.com"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s

  # Shadowpulse Python application
  app:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: shadowpulse-app
    environment:
      # Point to Elasticsearch service instead of localhost
      - ES_HOST=http://elasticsearch:9200
      # Point to Tor service instead of localhost
      - TOR_PROXY_IP=tor
      - TOR_PORT=9050
    ports:
      - "8501:8501"
    depends_on:
      elasticsearch:
        condition: service_healthy
      tor:
        condition: service_healthy
    volumes:
      # Mount current directory for live code changes during development
      - .:/app
    networks:
      - shadowpulse-network
    command: streamlit run dashboard.py --server.port=8501 --server.address=0.0.0.0

volumes:
  elasticsearch_data:
    driver: local

networks:
  shadowpulse-network:
    driver: bridge
```

---

## File 3: .dockerignore

Location: `/home/kali/shadowpulse/.dockerignore`

```
# Git and version control
.git
.gitignore
.github

# Python
__pycache__
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
.venv
.env
*.egg-info/
dist/
build/

# IDEs
.vscode
.idea
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Project-specific
elasticsearch-8.13.2/
*.log
.streamlit/
debug_*.py
wipe_db.py
```

---

## File 4: config.py (MODIFIED)

Location: `/home/kali/shadowpulse/config.py`

**Only the top section was modified. Show the changed lines:**

```python
import os

# Tor Settings
# In Docker: environment variable points to 'tor' service name
# Locally: defaults to localhost
TOR_PROXY_IP = os.getenv("TOR_PROXY_IP", "127.0.0.1")
TOR_PORT = int(os.getenv("TOR_PORT", "9050"))

# Elasticsearch Settings
# In Docker: environment variable points to 'elasticsearch' service name
# Locally: defaults to localhost
ES_HOST = os.getenv("ES_HOST", "http://127.0.0.1:9200")
INDEX_NAME = "shadowpulse_index"

# User agents
USER_AGENTS = [
    # ... rest of the file unchanged ...
]
```

**Change summary:**
- Added `import os` at the top
- Changed `TOR_PROXY_IP = "127.0.0.1"` to `TOR_PROXY_IP = os.getenv("TOR_PROXY_IP", "127.0.0.1")`
- Changed `TOR_PORT = 9050` to `TOR_PORT = int(os.getenv("TOR_PORT", "9050"))`
- Changed `ES_HOST = "http://127.0.0.1:9200"` to `ES_HOST = os.getenv("ES_HOST", "http://127.0.0.1:9200")`

---

## Summary of Changes

### New Files (6)
1. ✅ `Dockerfile` - Container build recipe
2. ✅ `docker-compose.yml` - Service orchestration
3. ✅ `.dockerignore` - Build optimization
4. ✅ `DOCKERIZATION_COMPLETE.md` - Project summary
5. ✅ `DOCKER_SETUP.md` - User guide for coworkers
6. ✅ `DOCKER_MIGRATION.md` - Technical reference
7. ✅ `DOCKER_QUICK_REFERENCE.md` - Command cheatsheet
8. ✅ `docker-test.sh` - Validation script

### Modified Files (1)
1. ⚠️ `config.py` - Added environment variable support (first 12 lines)

### Unchanged Files
All other files (`dashboard.py`, `database.py`, `tor_network.py`, `search_engine.py`, `scraper.py`, etc.) work as-is without modifications!

---

## How to Use These Files

### For You (Developer)
```bash
cd /home/kali/shadowpulse

# Validate everything is set up correctly
bash docker-test.sh

# Build the Docker image
docker-compose build

# Start all services
docker-compose up

# Open http://localhost:8501 in your browser
```

### For Your Coworkers
```bash
# Clone your repo
git clone <your-repo>
cd shadowpulse

# Start everything (Docker handles the rest)
docker-compose up

# Open http://localhost:8501
```

**They don't need:**
- Python 3.10 installed
- Elasticsearch downloaded
- Tor service running
- Virtual environment setup

**Docker handles it all automatically!**

---

## Verification

Run `bash docker-test.sh` to verify all files are correctly set up:

```bash
✅ Docker installed
✅ Docker Compose installed
✅ Dockerfile present
✅ docker-compose.yml present and valid
✅ requirements.txt present
✅ config.py uses os.getenv
✅ Ports 8501, 9200, 9050 available
```

If all checks pass, you're ready to run:
```bash
docker-compose up
```

---

## Key Differences: Local vs Docker

| Aspect | Local | Docker |
|--------|-------|--------|
| Elasticsearch | `http://127.0.0.1:9200` | `http://elasticsearch:9200` |
| Tor | `127.0.0.1:9050` | `tor:9050` |
| Config | Defaults in `config.py` | Environment vars in `docker-compose.yml` |
| Port 8501 | Not open | `0.0.0.0:8501` (accessible from anywhere) |

**Your code works identically in both modes!** The environment variables in `config.py` handle the switching automatically.

