# 🐳 Shadowpulse Docker - Quick Reference Card

## One-Liners

| Task | Command |
|------|---------|
| **Start everything** | `docker-compose up` |
| **Start in background** | `docker-compose up -d` |
| **Stop everything** | `docker-compose down` |
| **Rebuild image** | `docker-compose build` |
| **View all logs** | `docker-compose logs -f` |
| **View app logs only** | `docker-compose logs -f app` |
| **Check status** | `docker-compose ps` |
| **Delete all data** | `docker-compose down -v` |
| **Validate setup** | `bash docker-test.sh` |

---

## Service Ports

| Service | Port | From Host | Inside Docker |
|---------|------|-----------|---------------|
| Streamlit App | 8501 | `localhost:8501` | N/A |
| Elasticsearch | 9200 | `localhost:9200` | `elasticsearch:9200` |
| Tor SOCKS5 | 9050 | `localhost:9050` | `tor:9050` |

---

## Environment Variables

Set in `docker-compose.yml`, read by app from `config.py`:

```yaml
environment:
  - ES_HOST=http://elasticsearch:9200      # ← Service name, not localhost
  - TOR_PROXY_IP=tor                        # ← Service name, not localhost
  - TOR_PORT=9050
```

Your code in `config.py`:
```python
ES_HOST = os.getenv("ES_HOST", "http://127.0.0.1:9200")
TOR_PROXY_IP = os.getenv("TOR_PROXY_IP", "127.0.0.1")
```

**Local mode** (no env vars set) → Uses `127.0.0.1` defaults
**Docker mode** (env vars from compose) → Uses service names

---

## File Structure

```
shadowpulse/
├── Dockerfile                    ← Build instructions
├── docker-compose.yml            ← Service orchestration
├── .dockerignore                 ← Excludes large files from build
├── config.py                     ← MODIFIED: Now uses environment variables
├── dashboard.py                  ← No changes needed
├── database.py                   ← No changes needed
├── tor_network.py                ← No changes needed
├── DOCKERIZATION_COMPLETE.md     ← This project summary
├── DOCKER_SETUP.md               ← User guide for coworkers
├── DOCKER_MIGRATION.md           ← Technical reference
├── docker-test.sh                ← Validation script
└── requirements.txt              ← No changes needed
```

---

## Troubleshooting Quick Fix

### "Connection refused" on app startup
```bash
docker-compose down
docker-compose up --build
# Wait ~60 seconds for Elasticsearch and Tor to be ready
```

### "Port already in use"
```bash
# Find what's using the port:
lsof -i :8501
lsof -i :9200
lsof -i :9050

# Or change port in docker-compose.yml:
app:
  ports:
    - "8000:8501"  # Now accessible at localhost:8000
```

### "Service is not healthy"
```bash
docker-compose logs elasticsearch  # or 'tor' or 'app'
```

### App won't reload on code changes
```bash
# Ensure volume is mounted correctly:
docker-compose exec app ls -la /app
# Should show your Python files

# Restart Streamlit:
docker-compose restart app
```

---

## Docker Compose Cheat Sheet

```bash
# Build images
docker-compose build

# Start services (foreground, see logs)
docker-compose up

# Start services (background)
docker-compose up -d

# Stop services
docker-compose down

# Stop and delete volumes
docker-compose down -v

# View logs
docker-compose logs              # All logs
docker-compose logs -f app       # Follow app logs
docker-compose logs -f --tail 50 # Last 50 lines

# Check status
docker-compose ps

# Run command in running container
docker-compose exec app bash

# Scale a service
docker-compose up -d --scale app=3

# Remove unused resources
docker system prune -a
```

---

## For Coworkers: Copy-Paste Instructions

```bash
# 1. Get the code
git clone <your-repository>
cd shadowpulse

# 2. Start services
docker-compose up

# 3. Wait ~60 seconds, then open browser
open http://localhost:8501
# or
firefox http://localhost:8501
```

**That's literally it.** No prerequisites except Docker Desktop.

---

## Performance Notes

- **First build:** 2-3 minutes
- **Subsequent starts:** 30-60 seconds
- **Memory usage:** ~1 GB
- **Disk usage:** ~2 GB (image + data)

---

## What Each File Does

### `Dockerfile`
Builds the Python app container image:
- Starts with `python:3.10-slim` (166 MB base)
- Installs dependencies from `requirements.txt`
- Adds `curl` for health checks
- Runs app on port 8501

### `docker-compose.yml`
Orchestrates three services:
1. **elasticsearch** - Database
2. **tor** - Proxy
3. **app** - Your Python application

Services communicate via Docker's internal network using service names.

### `config.py` (Modified)
Reads environment variables from Docker, with localhost defaults for local development:
```python
import os
ES_HOST = os.getenv("ES_HOST", "http://127.0.0.1:9200")
TOR_PROXY_IP = os.getenv("TOR_PROXY_IP", "127.0.0.1")
```

### `.dockerignore`
Excludes files from Docker build context:
- Large files like `elasticsearch-8.13.2/` (saves 600 MB)
- Cache files like `__pycache__/`
- Git files

Faster builds = happier developers!

### `docker-test.sh`
Pre-flight validation:
```bash
bash docker-test.sh
```
Checks Docker installation, file presence, ports, configuration.

---

## Health Checks

Each service includes a health check that must pass before dependents start:

```
elasticsearch → passes health check (curl to 9200)
    ↓
tor → passes health check (curl through proxy)
    ↓
app → can now start safely
```

Wait times:
- Elasticsearch: 30 seconds until healthy
- Tor: 15 seconds until healthy
- App: 10-20 seconds to start
- **Total:** ~60 seconds from `docker-compose up` to app ready

---

## Testing Connectivity from Host

```bash
# Test Elasticsearch
curl http://localhost:9200

# Test Tor (should return your proxy IP, not real IP)
curl -x socks5://localhost:9050 http://ipv4.icanhazip.com

# Test Streamlit app
curl http://localhost:8501/_stcore/health
```

All three should succeed without errors.

---

## Next Steps

1. ✅ Run `bash docker-test.sh` (validation)
2. ✅ Run `docker-compose build` (build image)
3. ✅ Run `docker-compose up` (start services)
4. ✅ Open `http://localhost:8501` (use app)
5. ✅ Share with coworkers!

---

**Questions?** Check `DOCKER_SETUP.md` (user guide) or `DOCKER_MIGRATION.md` (technical details).

