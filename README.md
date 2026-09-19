# Shadowpulse

Automated Dark Web CTI Engine | Python, Tor, Gemini API, Elasticsearch, Docker

Shadowpulse is a dark-web cyber threat intelligence platform designed to automate collection, enrichment, and structured CTI extraction from hidden services. The system routes searches through Tor, crawls onion targets, strips noisy forum content, and feeds extracted intelligence into a Gemini-based AI pipeline before indexing findings in Elasticsearch and exposing them through a Streamlit dashboard.

## What the platform does

- Anonymized Scraping Engine: Built around Tor SOCKS5 proxying and circuit-aware request handling to safely query and crawl ephemeral dark web services.
- Resilient AI Pipeline: Uses a 5-tier Google Gemini fallback chain with proxy isolation to enforce structured JSON extraction of threat actors, MITRE ATT&CK techniques, malware, victims, and IOCs.
- CTI Preprocessing & Indexing: Cleans raw HTML/forum content, extracts indicators such as IPs, hashes, wallet addresses, CVEs, and URLs, and stores normalized payloads in Elasticsearch.
- Architecture Deployment: Runs as a multi-service Docker Compose stack with a Streamlit UI for live monitoring and analyst-driven threat investigation.

## Core capabilities

- Parallel onion search across multiple dark-web indexes via Tor-enabled requests
- Search result validation, URL health checks, and offline retry protection
- HTML noise stripping and structured IOC extraction from crawled content
- Threat intelligence normalization into JSON and STIX 2.1-compatible outputs
- Real-time dashboard views for telemetry, link status, and CTI extraction results
- Elasticsearch-backed persistence for operational history and stored findings

## Tech stack

- Python
- Tor SOCKS5 proxying
- Google Gemini API (google-genai)
- Elasticsearch
- Docker / Docker Compose
- Streamlit
- Requests, BeautifulSoup, pandas, altair
- STIX 2.1 export support

## Architecture overview

1. Search layer
  - Queries known onion search engines and dark-net directories through Tor.
2. Proxy & network layer
  - Forces outbound traffic through the Tor SOCKS5 proxy and applies connection/circuit safeguards.
3. Crawl & preprocessing layer
  - Downloads pages, strips HTML noise, extracts raw content, and normalizes indicators.
4. AI extraction layer
  - Sends cleaned text to a Gemini client with a fallback model chain for schema-validated CTI extraction.
5. Storage & analytics layer
  - Stores structured results and metadata in Elasticsearch and visualizes them via Streamlit.
6. Export layer
  - Produces STIX 2.1 and JSON artifacts suitable for downstream TI workflows.

## Repository layout

- `app.py` — Streamlit application entrypoint
- `main.py` — project startup and orchestration entrypoint
- `src/` — core networking, crawling, indexing, and dashboard logic
- `ai/` — Gemini client, schemas, and CTI extraction helpers
- `docker/` — container configuration and Tor settings
- `tests/` — pipeline and exporter validation tests

## Requirements

- Docker and Docker Compose
- Python 3.10+
- A valid Gemini API key for the LLM extraction pipeline

## Quick start

Clone the repository:

```bash
git clone https://github.com/ghassen5888/Shadowpulse.git
cd shadowpulse
```

Create a local environment file with your Gemini configuration:

```bash
cp .env.example .env
```

If `.env.example` is not present, create `.env` manually with values similar to:

```bash
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.5-flash
ES_HOST=http://127.0.0.1:9200
TOR_PROXY_IP=127.0.0.1
TOR_PORT=9050
```

Start the full stack:

```bash
docker compose up --build -d
```

Access the dashboard:

```text
http://localhost:8501
```

Verify services:

```bash
docker compose ps
curl http://localhost:9200
```

## Configuration

The project reads its settings from environment variables and defaults for local and containerized execution. Key variables include:

- `TOR_PROXY_IP` — Tor proxy host
- `TOR_PORT` — Tor SOCKS proxy port (default: 9050)
- `ES_HOST` — Elasticsearch endpoint
- `GEMINI_API_KEY` — API key used by the Gemini client
- `GEMINI_MODEL` — primary model name in the fallback chain
- `OFFLINE_RETRY_COOLDOWN_HOURS` — cooldown period for dead onion targets

## Typical workflow

1. Create an investigation thread or operation in the dashboard.
2. Search for a keyword, threat actor, or malware family.
3. Shadowpulse queries onion search engines through Tor.
4. The crawler validates and scrapes active targets.
5. The content is cleaned and parsed for CTI indicators.
6. Gemini extracts structured intelligence (threat actors, attack techniques, victims, summary, etc.).
7. Results are indexed in Elasticsearch and surfaced in the UI.
8. CTI data can be exported as STIX 2.1 and JSON bundles.

## Data processing notes

- Raw forum and page HTML is normalized to remove noise before CTI extraction.
- Indicator extraction focuses on actionable signals such as:
 - IP addresses
 - file hashes
 - cryptocurrency wallet addresses
 - CVEs
 - URLs / onion links
 - email addresses
- Gemini output is validated against a strict JSON schema before being accepted by the pipeline.

## Security and legal use

This project is intended for authorized cybersecurity research, threat hunting, and defensive intelligence workflows. Use it only in compliance with local laws, organizational policies, and relevant legal constraints.

Do not bypass the Tor proxy or run the stack on untrusted or non-anonymized networks.

## License

This project is provided as-is for research and internal security operations. Review the repository license before production deployment or redistribution.