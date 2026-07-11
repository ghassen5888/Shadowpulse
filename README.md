🕵*** Shadowpulse: Dark Web Threat Intelligence Platform***

Shadowpulse is an advanced, concurrent Cyber Threat Intelligence (CTI) platform designed to scrape, analyze, and catalog dark web telemetry. By routing multi-threaded search operations through a Tor SOCKS5 proxy, it safely aggregates Open-Source Intelligence (OSINT) from hidden services (.onion domains) and exports the data in enterprise-standard STIX 2.1 bundles.

***Key Features***

Parallel Dark Web Scanning: Utilizes advanced Python threading (ThreadPoolExecutor) to query multiple onion search engines concurrently without freezing the UI.

True Anonymity Routing: Strictly routes all HTTP requests and DNS resolutions through a local Tor proxy (socks5h://) to prevent DNS leaks and ensure operational security.

Elasticsearch Backend: High-performance storage of operational threads, scraped raw data, and historical threat indicators.

Live Telemetry & Diagnostics: Real-time UI progress bars and a thread-safe telemetry buffer to monitor Tor circuit health, connection latency, and HTTP statuses.

STIX 2.1 Integration: Automatically packages gathered intel (Indicators, Observed Data, and Relationships) into universally accepted OASIS STIX 2.1 JSON bundles for SIEM integration.

***Technologies Used***

**Frontend & UI:**

*Streamlit*: Powers the real-time, interactive analyst dashboard (st.session_state, custom fragments, Altair charts).

*Altair / Pandas*: Data visualization for global operation statistics and active/dead link ratios.

**Core Engine & Networking**

*Python 3.10+*: Core backend engine.

*Tor (SOCKS5 Proxy)*: Provides the anonymity layer.

*Requests / HTTPAdapter*: Configured with advanced retry logic, connection pooling, and strict timeouts to handle the unstable nature of the dark web.

*Concurrent Futures*: Asynchronous multi-threading for blazing-fast parallel web scraping.

**Database & Standards:**

*Elasticsearch*: Fast, scalable NoSQL document store for archiving scraped HTML and thread metadata.

*STIX 2.1 (stix2 Python SDK)*: Standardized threat intelligence formatting.

***Installation & Setup***

Shadowpulse is designed to run in an isolated containerized environment to ensure proxy rules are strictly enforced.

Prerequisites

Docker & Docker Compose

Git

Quick Start

Clone the repository:

git clone https://github.com/ghassen5888/Shadowpulse.git
cd shadowpulse


Start the environment:
Bring up the Streamlit App, Tor Proxy, and Elasticsearch containers.

docker compose up --build -d


Verify Tor Circuit:
Ensure the Tor network is bootstrapped by checking the proxy container logs.

docker logs shadowpulse-tor -f


Access the Dashboard:
Open your browser and navigate to:
http://localhost:8501

 ***How to Use the Platform***

1. Create an Operation (Thread)

On the left sidebar, enter a name under New Operation Name (e.g., Op Red Sparrow) and click Create Operation. This acts as your isolated workspace/case file.

2. Scan & Attach Intelligence

In the main window, type a search term or threat actor name into the Add Intel search bar.

Click Scan & Attach.

Shadowpulse will spawn background workers to query up to 17 dark web engines simultaneously. The progress bar will update in real-time.

Once completed, discovered .onion links are automatically saved to the Elasticsearch database and attached to your active Operation.

3. Monitor Link Health

Use the Check Link Status (Ping All) button to run a concurrent HEAD request against all attached links. A pie chart will dynamically update to show which .onion endpoints are still active and which are currently offline.

4. Deep Crawl

Click the Deep Crawl button next to any active link. The platform will perform a full HTTP GET request, scrape the raw HTML of the hidden service, and archive it directly into the Elasticsearch case file for safe, offline reading.

5. Export STIX 2.1 (SIEM Integration)

(If enabled in UI) Analysts can export the Operation's findings. Shadowpulse generates a .json file containing Identity, Indicator, Observed-Data, and Relationship objects, ready to be ingested by enterprise firewalls or Threat Intelligence Platforms (TIPs).

⚠️ ***Disclaimer & OpSec Warning***

This tool is built for authorized cybersecurity research, threat hunting, and intelligence gathering. Ensure you comply with all local laws and organizational policies when accessing the dark web.
Never bypass the Tor container proxy or run the engine on a personal, un-proxied network connection.
