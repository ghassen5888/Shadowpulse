# Shadowpulse Docker Setup Guide

## Overview

This guide explains how to run Shadowpulse using Docker Compose, which automatically manages Elasticsearch, Tor, and the Python application in isolated containers.

## Quick Start

### Prerequisites
- Docker Desktop (or Docker + Docker Compose installed)
- No Elasticsearch, Tor, or Python venv setup required!

### Running Shadowpulse

```bash
# Navigate to the shadowpulse directory
cd /path/to/shadowpulse

# Start all services (Elasticsearch, Tor, App)
docker-compose up

# Open your browser and go to: http://localhost:8501
```

That's it! Docker handles everything.

### Stopping the Application

```bash
# Stop all services (gracefully)
docker-compose down

# Stop and remove volumes (WARNING: deletes Elasticsearch data)
docker-compose down -v
```

---

## How It Works

### Services Architecture

```
┌─────────────────────────────────────────────────┐
│         Docker Network (shadowpulse-network)    │
├────────────────────┬──────────────┬─────────────┤
│                    │              │             │
│  elasticsearch:9200│   tor:9050   │   app:8501  │
│  (DB)              │  (Proxy)     │ (Streamlit) │
│                    │              │             │
└────────────────────┴──────────────┴─────────────┘
```

### Key Changes from Local Setup

#### 1. **Networking**
- **Locally:** Services use `localhost` (127.0.0.1)
- **Docker:** Services use container names (`elasticsearch`, `tor`, `app`)
  - Docker's internal DNS resolves `elasticsearch` → IP of elasticsearch container
  - Docker's internal DNS resolves `tor` → IP of tor container

#### 2. **Configuration (Environment Variables)**
The `docker-compose.yml` passes environment variables to the app:
```yaml
environment:
  - ES_HOST=http://elasticsearch:9200    # Instead of localhost
  - TOR_PROXY_IP=tor                      # Instead of 127.0.0.1
  - TOR_PORT=9050
```

Your `config.py` now reads from these environment variables:
```python
import os
TOR_PROXY_IP = os.getenv("TOR_PROXY_IP", "127.0.0.1")  # Defaults to localhost
TOR_PORT = int(os.getenv("TOR_PORT", "9050"))
ES_HOST = os.getenv("ES_HOST", "http://127.0.0.1:9200")  # Defaults to localhost
```

**This means your code works both locally AND in Docker without any changes at runtime!**

---

## File-by-File Changes

### 1. **`config.py`** (Modified)
Added support for environment variables with sensible defaults:
```python
import os

TOR_PROXY_IP = os.getenv("TOR_PROXY_IP", "127.0.0.1")  # ← Changed
TOR_PORT = int(os.getenv("TOR_PORT", "9050"))          # ← Changed
ES_HOST = os.getenv("ES_HOST", "http://127.0.0.1:9200")  # ← Changed
INDEX_NAME = "shadowpulse_index"
```

**Why this matters:**
- **In Docker:** Environment variables in `docker-compose.yml` override defaults
- **Locally (for testing):** Defaults to `localhost` so existing local setup still works

### 2. **`Dockerfile`** (New)
Builds a lightweight Python image:
- Uses `python:3.10-slim` (only 166 MB vs 1 GB for full Python)
- Installs dependencies from `requirements.txt` (all use pre-compiled wheels)
- Only adds `curl` for health checks (no gcc or build tools needed)
- Runs as non-root user (`shadowuser`) for security
- Exposes Streamlit on port 8501

### 3. **`docker-compose.yml`** (New)
Orchestrates three services:

#### Service: `elasticsearch`
```yaml
image: elasticsearch:8.13.2
environment:
  - discovery.type=single-node      # Single-node cluster
  - xpack.security.enabled=false    # Security disabled (matches your local setup)
  - ES_JAVA_OPTS=-Xms512m -Xmx512m  # 512 MB memory limit
ports:
  - "9200:9200"                     # Accessible from host machine
volumes:
  - elasticsearch_data:/...         # Persistent data directory
healthcheck:                        # Wait for ES to be ready
  test: ["CMD", "curl", "-f", "http://localhost:9200"]
  ...
```

#### Service: `tor`
```yaml
image: peterdavehello/tor-socks-proxy:latest
ports:
  - "9050:9050"                     # Accessible from host machine
healthcheck:                        # Verify Tor is accepting connections
  test: ["CMD", "curl", "-f", "-x", "socks5://127.0.0.1:9050", "..."]
  ...
```

#### Service: `app`
```yaml
build: .                            # Build from local Dockerfile
environment:
  - ES_HOST=http://elasticsearch:9200  # Service name, not localhost
  - TOR_PROXY_IP=tor                   # Service name, not localhost
  - TOR_PORT=9050
depends_on:
  elasticsearch:
    condition: service_healthy      # Wait for Elasticsearch to be healthy
  tor:
    condition: service_healthy      # Wait for Tor to be healthy
ports:
  - "8501:8501"                     # Streamlit accessible from host
volumes:
  - .:/app                          # Mount source for live development
```

---

## Accessing Services from Host Machine

Once running, services are accessible:

| Service | Host URL | Notes |
|---------|----------|-------|
| Streamlit App | `http://localhost:8501` | Open in browser |
| Elasticsearch | `http://localhost:9200` | HTTP requests from host |
| Tor SOCKS5 | `localhost:9050` | Can be used from host machine too |

---

## Development Workflow

### Making Code Changes

Since `docker-compose.yml` mounts your local directory as a volume:
```yaml
volumes:
  - .:/app  # Live code synchronization
```

**Any Python file changes are automatically reflected in the running container.**

Simply save your code → Streamlit hot-reloads → No rebuild needed!

### Rebuilding the Docker Image

If you change `Dockerfile` or `requirements.txt`:
```bash
docker-compose build --no-cache
docker-compose up
```

---

## Troubleshooting

### "Service is not healthy"
```bash
# Check service logs
docker-compose logs elasticsearch  # or 'tor' or 'app'

# Wait longer before starting dependent services
# Adjust healthcheck timing in docker-compose.yml if needed
```

### "Connection refused" errors in app logs
- **Elasticsearch:** Ensure `elasticsearch` service is running: `docker-compose logs elasticsearch`
- **Tor:** Ensure `tor` service is running: `docker-compose logs tor`
- **Port conflicts:** If ports 9200, 9050, or 8501 are already in use, modify them in `docker-compose.yml`

### Database data persists between runs
```bash
# Data is stored in Docker volume 'elasticsearch_data'
# To reset the database:
docker-compose down -v  # -v removes volumes
docker-compose up       # Fresh start
```

### Container uses too much memory
Elasticsearch is configured with `-Xms512m -Xmx512m` (512 MB max).
Adjust in `docker-compose.yml` if needed:
```yaml
environment:
  - ES_JAVA_OPTS=-Xms256m -Xmx256m  # Reduce to 256 MB
```

---

## Advanced: Testing Local vs Docker

### Run locally (without Docker)
```bash
# Terminal 1: Start Elasticsearch
./elasticsearch-8.13.2/bin/elasticsearch

# Terminal 2: Start Tor
sudo service tor start

# Terminal 3: Start app (will use 127.0.0.1 defaults from config.py)
source venv/bin/activate
streamlit run dashboard.py
```

### Run in Docker
```bash
docker-compose up
```

**The code works identically in both environments because `config.py` uses environment variables with sensible defaults!**

---

## Performance Notes

### Build Time
- **First build:** ~2-3 minutes (downloads base image, installs dependencies)
- **Subsequent builds:** ~10-30 seconds (layers cached)

### Memory Usage
- **Elasticsearch:** 512 MB (configurable)
- **Tor:** ~50-100 MB
- **Python App:** ~200-300 MB
- **Total:** ~1 GB (can be reduced by adjusting Elasticsearch JVM)

### Network
- **Services communicate via Docker's internal network** (very fast, same machine)
- **No localhost overhead** compared to local setup
- **Tor SOCKS5 proxy still routes to real onion network** (same as local)

---

## Next Steps

1. **Deploy to production:** Use `docker-compose -f docker-compose.prod.yml up` (separate production config with persistence, logging, etc.)
2. **Add monitoring:** Integrate with Prometheus + Grafana for metrics
3. **Add authentication:** Run Elasticsearch with X-Pack security enabled and configure credentials
4. **Scale Tor:** Run multiple Tor containers for load balancing (requires custom config)

