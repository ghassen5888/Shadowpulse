# Code Changes Summary for Docker Migration

## Modified Files

### 1. `config.py` - Environment Variable Support

**Before:**
```python
TOR_PROXY_IP = "127.0.0.1"
TOR_PORT = 9050
ES_HOST = "http://127.0.0.1:9200"
INDEX_NAME = "shadowpulse_index"
```

**After:**
```python
import os

TOR_PROXY_IP = os.getenv("TOR_PROXY_IP", "127.0.0.1")
TOR_PORT = int(os.getenv("TOR_PORT", "9050"))
ES_HOST = os.getenv("ES_HOST", "http://127.0.0.1:9200")
INDEX_NAME = "shadowpulse_index"
```

**How it works:**
- `os.getenv("TOR_PROXY_IP", "127.0.0.1")` reads the environment variable `TOR_PROXY_IP`
- If not found, defaults to `"127.0.0.1"` (localhost)
- In Docker: `docker-compose.yml` sets `TOR_PROXY_IP=tor` and `ES_HOST=http://elasticsearch:9200`
- Locally: No environment variables set → uses defaults (localhost)

**No other files need to be changed!** Your code in `tor_network.py`, `database.py`, etc., already uses these config values correctly.

---

## New Files

### 1. `Dockerfile`
Creates a lightweight Docker image for the Python app.

**Key optimizations:**
- `python:3.10-slim` base image (166 MB)
- No build tools (gcc, build-essential) installed
- Only `curl` added for health checks
- Pre-compiled wheels in `requirements.txt` (pandas, streamlit all have wheels)
- Non-root user `shadowuser` for security
- Health check configured

**Build:** `docker build -t shadowpulse:latest .`
**Size:** ~450-500 MB (lightweight for CI/CD)

### 2. `docker-compose.yml`
Orchestrates three services with proper networking and health checks.

**Three services:**
1. **elasticsearch** - Uses official Elasticsearch 8.13.2 image
2. **tor** - Uses `peterdavehello/tor-socks-proxy` (verified to expose port 9050)
3. **app** - Built from local Dockerfile with environment variables

**Key features:**
- Services communicate via Docker internal network (no localhost needed)
- Health checks ensure services start in order
- Volumes for persistent Elasticsearch data
- Port mappings for host access (9200, 9050, 8501)
- Environment variables passed to app service

### 3. `.dockerignore`
Excludes unnecessary files from Docker build context.

**Excludes:**
- `__pycache__/` (speeds up build)
- `elasticsearch-8.13.2/` (large, not needed in container)
- `.git/`, `venv/`, etc.

---

## How Services Find Each Other

### In Docker (Container-to-Container)

```
┌─────────────────────────────────────────────────────────┐
│          Docker Internal Network                        │
│  (Docker DNS resolves service names automatically)      │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  app container                                           │
│  ├─ ES_HOST=http://elasticsearch:9200                   │
│  │   └─ Docker DNS resolves "elasticsearch" → ES IP    │
│  ├─ TOR_PROXY_IP=tor                                    │
│  │   └─ Docker DNS resolves "tor" → Tor IP            │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

**How Docker DNS works:**
1. App makes request to `http://elasticsearch:9200/`
2. Docker's embedded DNS (127.0.0.11:53) intercepts
3. Resolves "elasticsearch" → IP of elasticsearch container
4. Connection succeeds within the network

### From Host Machine (Outside Docker)

```
localhost:9200   → Elasticsearch (port mapping 9200:9200)
localhost:9050   → Tor proxy (port mapping 9050:9050)
localhost:8501   → Streamlit app (port mapping 8501:8501)
```

---

## No Code Changes Needed In

These files already work correctly with environment variables from `config.py`:

- ✅ `database.py` - Uses `config.ES_HOST`
- ✅ `tor_network.py` - Uses `config.TOR_PROXY_IP` and `config.TOR_PORT`
- ✅ `search_engine.py` - Uses `tor_network` module
- ✅ `dashboard.py` - Uses `tor_network` and `database` modules
- ✅ `scraper.py` - Uses `tor_network`

All these modules read from `config.py`, which now supports environment variables!

---

## Testing the Setup

### 1. Verify Docker installation
```bash
docker --version
docker-compose --version
```

### 2. Build the image
```bash
cd /path/to/shadowpulse
docker-compose build
```

### 3. Start all services
```bash
docker-compose up
```

### 4. Check service status
```bash
docker-compose ps
# Should show all 3 services as "Up"

docker-compose logs app
# Should show Streamlit server starting on port 8501
```

### 5. Test connectivity
```bash
# From another terminal
curl http://localhost:9200               # Elasticsearch
curl -x socks5://localhost:9050 http://ipv4.icanhazip.com  # Tor
curl http://localhost:8501/_stcore/health  # App health
```

### 6. Open the app
```
http://localhost:8501
```

---

## Deployment Notes

### For Coworkers

Share these commands:
```bash
git clone <your-repo>
cd shadowpulse
docker-compose up
```

That's it! No prerequisites except Docker Desktop.

### For CI/CD Pipeline

```bash
docker build -t shadowpulse:latest .
docker run -d \
  -e ES_HOST=http://elasticsearch:9200 \
  -e TOR_PROXY_IP=tor \
  -p 8501:8501 \
  shadowpulse:latest
```

### Production Considerations

For production, consider:
1. **Separate docker-compose.prod.yml** with:
   - Elasticsearch security enabled (xpack.security.enabled=true)
   - Credentials in `.env` file (not docker-compose.yml)
   - Persistent volumes on separate disk
   - Resource limits and logging
2. **Health check timeouts** may need adjustment for slower networks
3. **Memory limits** for Elasticsearch can be reduced if using small instance

---

## Environment Variable Reference

| Variable | Docker Value | Local Value | Used In |
|----------|--------------|-------------|---------|
| `ES_HOST` | `http://elasticsearch:9200` | `http://127.0.0.1:9200` | database.py |
| `TOR_PROXY_IP` | `tor` | `127.0.0.1` | tor_network.py |
| `TOR_PORT` | `9050` | `9050` | tor_network.py |

---

## Troubleshooting Checklist

- [ ] Docker Desktop running? (`docker ps`)
- [ ] Port 9200 (ES), 9050 (Tor), 8501 (app) not in use?
- [ ] Build succeeds? (`docker-compose build`)
- [ ] Services start? (`docker-compose up`)
- [ ] No "Connection refused" errors? (`docker-compose logs`)
- [ ] App accessible at http://localhost:8501?

