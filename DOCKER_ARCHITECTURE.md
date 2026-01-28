# Shadowpulse Docker Architecture & Networking

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         HOST MACHINE                                 │
│                     (Your Development PC)                            │
│                                                                       │
│  Browser: http://localhost:8501                                     │
│      ↓                                                               │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │              DOCKER DAEMON (Engine)                            │ │
│  │                                                                │ │
│  │  ┌────────────────────────────────────────────────────────┐  │ │
│  │  │   Docker Network: shadowpulse-network (bridge)         │  │ │
│  │  │                                                        │  │ │
│  │  │  ┌─────────────────┐  ┌──────────────┐  ┌──────────┐ │  │ │
│  │  │  │ elasticsearch   │  │    tor       │  │   app    │ │  │ │
│  │  │  │                 │  │              │  │          │ │  │ │
│  │  │  │ Container ID    │  │ Container ID │  │Container │ │  │ │
│  │  │  │ Name: elasticse │  │ Name: tor    │  │ ID       │ │  │ │
│  │  │  │ -arch...        │  │              │  │ Name:    │ │  │ │
│  │  │  │                 │  │              │  │ app      │ │  │ │
│  │  │  │ Image:          │  │ Image:       │  │          │ │  │ │
│  │  │  │ elastic...8.13  │  │ tor-socks    │  │ Build    │ │  │ │
│  │  │  │                 │  │ -proxy       │  │ custom   │ │  │ │
│  │  │  │ Port: 9200      │  │ Port: 9050   │  │ Docker-  │ │  │ │
│  │  │  │                 │  │              │  │ file     │ │  │ │
│  │  │  │ Volume:         │  │ Volume:      │  │ Port:    │ │  │ │
│  │  │  │ elasticsearch_  │  │ (none)       │  │ 8501     │ │  │ │
│  │  │  │ data (persist)  │  │              │  │          │ │  │ │
│  │  │  └────────┬────────┘  └──────┬───────┘  └────┬─────┘ │  │ │
│  │  │           │                  │               │       │  │ │
│  │  │  DNS Resolution (Docker internal):          │       │  │ │
│  │  │  - "elasticsearch" → Container IP           │       │  │ │
│  │  │  - "tor" → Container IP                     │       │  │ │
│  │  │  - "app" → Container IP                     │       │  │ │
│  │  │           │                  │               │       │  │ │
│  │  └───────────┼──────────────────┼───────────────┼───────┘  │ │
│  │              │                  │               │          │ │
│  │  Port Mapping (Host → Container):              │          │ │
│  │  - 9200 → 9200                                 │          │ │
│  │  - 9050 → 9050                                 │          │ │
│  │  - 8501 → 8501 ◄─────────────────────────────┘          │ │
│  │                                                            │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  Host Network: localhost                                         │
│  - http://localhost:8501   (Streamlit)                          │
│  - http://localhost:9200   (Elasticsearch)                      │
│  - socks5://localhost:9050 (Tor proxy)                          │
│                                                                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Service Startup Sequence

```
docker-compose up
        ↓
   ┌────────────────────────────┐
   │ 1. Check if image exists   │
   │    (if not, build from     │
   │     Dockerfile)            │
   └────────────┬───────────────┘
                ↓
   ┌────────────────────────────┐
   │ 2. Create network          │
   │    shadowpulse-network     │
   └────────────┬───────────────┘
                ↓
   ┌────────────────────────────┐
   │ 3. Start elasticsearch     │
   │                            │
   │ Running health check:      │
   │ curl http://localhost:9200 │
   │                            │
   │ Status: Waiting (30s)      │
   └────────────┬───────────────┘
                ↓
   ┌────────────────────────────┐
   │ elasticsearch health ✅     │
   │ Healthy!                   │
   └────────────┬───────────────┘
                ↓
   ┌────────────────────────────┐
   │ 4. Start tor               │
   │                            │
   │ Running health check:      │
   │ curl -x socks5://...       │
   │                            │
   │ Status: Waiting (15s)      │
   └────────────┬───────────────┘
                ↓
   ┌────────────────────────────┐
   │ tor health ✅              │
   │ Healthy!                   │
   └────────────┬───────────────┘
                ↓
   ┌────────────────────────────┐
   │ 5. Start app               │
   │                            │
   │ Dependencies met:          │
   │ ✓ elasticsearch healthy    │
   │ ✓ tor healthy              │
   │                            │
   │ Running health check:      │
   │ curl http://localhost:8501/│
   │ _stcore/health             │
   │                            │
   │ Status: Waiting (20s)      │
   └────────────┬───────────────┘
                ↓
   ┌────────────────────────────┐
   │ app health ✅              │
   │ All services running!      │
   │                            │
   │ Open:                      │
   │ http://localhost:8501      │
   └────────────────────────────┘
   
Total time: ~60 seconds from "docker-compose up" to app ready
```

---

## Data Flow: App Connecting to Services

### Scenario 1: App Queries Elasticsearch

```
Python Code in dashboard.py:
    ├─ Imports: database.py
    ├─ Imports: config.py
    │
    └─ config.ES_HOST = "http://elasticsearch:9200"
            ↓
    Elasticsearch Client:
        client = Elasticsearch(config.ES_HOST)
            ↓
    Connection Request: http://elasticsearch:9200/
            ↓
    Docker Internal DNS (127.0.0.11:53):
        "elasticsearch" → resolves → 172.20.0.2 (example IP)
            ↓
    Network Request: http://172.20.0.2:9200/
            ↓
    elasticsearch container:
        Receives on port 9200
            ↓
    Response sent back to app
            ↓
    Result displayed in dashboard
```

**Key Point:** The name `elasticsearch` is automatically resolved by Docker's embedded DNS. No configuration needed beyond setting `ES_HOST=http://elasticsearch:9200` in `docker-compose.yml`.

---

### Scenario 2: App Routes Traffic Through Tor

```
Python Code in tor_network.py:
    ├─ Imports: config.py
    │
    └─ config.TOR_PROXY_IP = "tor"
       config.TOR_PORT = 9050
            ↓
    requests.Session configuration:
        session.proxies = {
            'http': 'socks5://tor:9050',
            'https': 'socks5://tor:9050'
        }
            ↓
    HTTP Request to .onion site via Tor:
        GET http://search.onion/...
            ↓
    Proxy configuration resolved:
        "tor:9050" → Docker DNS → 172.20.0.3 (example IP)
            ↓
    Connection: http://172.20.0.3:9050
            ↓
    tor container receives request
            ↓
    Tor proxy routes traffic through Tor network
            ↓
    Response returned through Tor
            ↓
    App receives .onion site content
```

---

## Configuration Propagation

```
docker-compose.yml (source of truth for Docker)
        ↓
    ┌───────────────────────────────────┐
    │ environment section for app:      │
    │                                   │
    │ - ES_HOST=...                    │
    │ - TOR_PROXY_IP=tor               │
    │ - TOR_PORT=9050                  │
    └─────────┬─────────────────────────┘
              ↓
    Docker container starts app service
    Sets environment variables in container:
        $ES_HOST = "http://elasticsearch:9200"
        $TOR_PROXY_IP = "tor"
        $TOR_PORT = "9050"
              ↓
    Python runtime loads config.py:
        
        import os
        ES_HOST = os.getenv("ES_HOST", ...)
        TOR_PROXY_IP = os.getenv("TOR_PROXY_IP", ...)
        TOR_PORT = int(os.getenv("TOR_PORT", ...))
              ↓
    config module variables now set to Docker values:
        ES_HOST = "http://elasticsearch:9200"
        TOR_PROXY_IP = "tor"
        TOR_PORT = 9050
              ↓
    Other modules import config and use these values:
        
        # In database.py:
        client = Elasticsearch(config.ES_HOST)  
        # Uses "http://elasticsearch:9200"
        
        # In tor_network.py:
        session.proxies = f'socks5://{config.TOR_PROXY_IP}:{config.TOR_PORT}'
        # Uses "socks5://tor:9050"
              ↓
    Services found and connected! ✅
```

---

## Local vs Docker Side-by-Side

```
┌──────────────────────────────┬──────────────────────────────┐
│        LOCAL SETUP           │       DOCKER SETUP           │
├──────────────────────────────┼──────────────────────────────┤
│                              │                              │
│ Terminal 1:                  │ Command:                     │
│ $ ./elasticsearch-8.13.2/... │ $ docker-compose up          │
│ ✓ Elasticsearch running      │                              │
│                              │ ✓ Elasticsearch service      │
│ Terminal 2:                  │ ✓ Tor service                │
│ $ sudo service tor start     │ ✓ App service                │
│ ✓ Tor running                │                              │
│                              │                              │
│ Terminal 3:                  │ Browser:                     │
│ $ source venv/bin/activate   │ http://localhost:8501        │
│ $ streamlit run dashboard.py │                              │
│ ✓ App running                │ Done!                        │
│                              │                              │
│ Browser:                     │                              │
│ http://localhost:8501        │ vs.                          │
│                              │                              │
│ Wait 5 minutes,              │ Wait 60 seconds,             │
│ manage 3 terminals,          │ 1 command                    │
│ handle Elasticsearch         │                              │
│ data directory issues        │ Works on any machine         │
│                              │ with Docker installed        │
│                              │                              │
└──────────────────────────────┴──────────────────────────────┘
```

---

## File Dependencies & Import Chain

```
dashboard.py (main entry point)
    ├── imports: config.py
    │       ├─ TOR_PROXY_IP = os.getenv("TOR_PROXY_IP", "127.0.0.1")
    │       ├─ TOR_PORT = int(os.getenv("TOR_PORT", "9050"))
    │       └─ ES_HOST = os.getenv("ES_HOST", "http://127.0.0.1:9200")
    │
    ├── imports: database.py
    │       └── imports: config.py
    │           └─ Uses: config.ES_HOST
    │               └─ Creates Elasticsearch client
    │
    ├── imports: tor_network.py
    │       └── imports: config.py
    │           └─ Uses: config.TOR_PROXY_IP, config.TOR_PORT
    │               └─ Creates Tor SOCKS session
    │
    ├── imports: search_engine.py
    │       └── imports: tor_network.py
    │           └─ Uses Tor session
    │
    └── imports: scraper.py
            └── imports: tor_network.py
                └─ Uses Tor session

Result: All modules use config.py settings ✅
        All modules work in Docker without changes ✅
```

---

## Volume Persistence

```
docker-compose.yml:
    ├─ elasticsearch:
    │   └─ volumes:
    │       └─ elasticsearch_data:/usr/share/elasticsearch/data
    │
    └─ app:
        └─ volumes:
            └─ .:/app  (development/live reload)


Elasticsearch Volume:
    ┌─────────────────────────────────┐
    │   Docker Volume                 │
    │   (managed by Docker)           │
    │                                 │
    │   ├─ indices/                   │
    │   │   └─ shadowpulse_index/    │
    │   │       └─ data files         │
    │   │                             │
    │   └─ _state/                    │
    │       └─ cluster state          │
    │                                 │
    └─────────────────────────────────┘
            ↑
            │ Persists between:
            │ - docker-compose down
            │ - docker-compose up
            │ - Restarts
            │
            X Deleted only with:
              docker-compose down -v


App Volume:
    ┌─────────────────────────────────┐
    │   Host Directory                │
    │   /home/kali/shadowpulse/       │
    │                                 │
    │   ├─ dashboard.py               │
    │   ├─ database.py                │
    │   ├─ config.py                  │
    │   └─ ...                        │
    │                                 │
    └─────────────────────────────────┘
            ↔ Live Sync
    
    Same files visible inside container at /app/
    
    ✅ Edit Python file on host
    ✅ File updates in container instantly
    ✅ Streamlit detects change
    ✅ App hot-reloads automatically
```

---

## Network Communication Paths

```
From App Container to Elasticsearch Container:
    
    app container (172.20.0.3:random_port)
            ↓
    Docker bridge network (shadowpulse-network)
            ↓
    Docker DNS intercepts: "http://elasticsearch:9200"
            ↓
    DNS resolution: "elasticsearch" → 172.20.0.2
            ↓
    Connection: 172.20.0.3 → 172.20.0.2:9200
            ↓
    elasticsearch container receives


From App Container to Host (if needed):
    
    app container → Docker gateway (172.20.0.1)
            ↓
    Host machine
            ↓
    localhost:9050 (if accessing Tor from host)
            
    BUT: Inside Docker, use "tor:9050" instead


From Host Machine to Services:
    
    Host: curl http://localhost:8501
            ↓
    Docker port mapping: 8501:8501
            ↓
    Container 172.20.0.3:8501
            ↓
    Response back to host
```

---

## Health Check Mechanism

```
Elasticsearch Health Check:
    Every 10 seconds:
    ┌────────────────────────┐
    │ Run: curl -f           │
    │      http://localhost:│
    │      9200              │
    └──────┬─────────────────┘
           ↓
    ┌────────────────────────┐
    │ Expected: HTTP 200     │
    │ Actual: HTTP 200       │
    │ Status: ✅ HEALTHY     │
    │                        │
    │ Dependents can start   │
    └────────────────────────┘


Tor Health Check:
    Every 30 seconds:
    ┌────────────────────────────────┐
    │ Run: curl -f                   │
    │      -x socks5://127.0.0.1:... │
    │      http://ipv4.icanhazip.com │
    └──────┬─────────────────────────┘
           ↓
    ┌────────────────────────────────┐
    │ Expected: HTTP 200             │
    │ Actual: HTTP 200               │
    │ Status: ✅ HEALTHY             │
    │                                │
    │ Dependents can start           │
    └────────────────────────────────┘


App Health Check:
    Every 30 seconds:
    ┌────────────────────────────────┐
    │ Run: curl -f                   │
    │      http://localhost:8501/    │
    │      _stcore/health            │
    └──────┬─────────────────────────┘
           ↓
    ┌────────────────────────────────┐
    │ Expected: HTTP 200             │
    │ Actual: HTTP 200               │
    │ Status: ✅ HEALTHY             │
    │                                │
    │ App verified running           │
    └────────────────────────────────┘

Dependency Order:
    elasticsearch HEALTHY
            ↓
    tor HEALTHY
            ↓
    app starts and becomes HEALTHY
            ↓
    ✅ System ready
```

---

## Docker Compose File Structure

```yaml
version: '3.8'  ← Compose file format version

services:       ← Define containers
  elasticsearch:
    image: ...  ← Use pre-built image
    environment ← Set env vars inside container
    ports:      ← Expose ports to host
    volumes:    ← Mount storage
    networks:   ← Join network
    healthcheck ← Check if running

  tor:
    image: ...
    ports:
    networks:
    healthcheck

  app:
    build: .    ← Build from Dockerfile instead of image
    environment ← Pass ES_HOST, TOR_PROXY_IP
    ports:
    depends_on: ← Wait for other services
    volumes:    ← Mount local code for development
    networks:

volumes:        ← Define persistent storage
  elasticsearch_data:

networks:       ← Define networks
  shadowpulse-network:
```

---

**This architecture ensures:**
- ✅ Services find each other reliably (no localhost issues)
- ✅ Code works identically local and in Docker
- ✅ No hard-coded IPs or ports
- ✅ Horizontal scaling possible (multiple instances)
- ✅ Easy onboarding (one `docker-compose up` command)

