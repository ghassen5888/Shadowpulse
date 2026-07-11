# dashboard.py
import math
import streamlit as st
import pandas as pd
import altair as alt  
from datetime import datetime
import time  
from src.config import settings as config
from src.database import database
from src.core import search_engine
from src.network import tor_network
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
from src.core.telemetry import TelemetryBuffer, render_telemetry_panel
from src.core.stix_exporter import export_stix_bundle_json

# --- Page Configuration ---
st.set_page_config(
    page_title="Shadowpulse Dashboard",
    page_icon="🕵️‍♂️",
    layout="wide"
)

#make sure tor is working
if "tor_initialized" not in st.session_state:
    with st.spinner("Initializing Anonymity Network..."):
         tor_network.setup_tor()
         tor_network.get_tor_session()
         st.session_state["tor_initialized"] = True 
         print("✅ Tor System Initialized Automatically")

# Initialize Session State
if "current_thread_id" not in st.session_state:
    st.session_state["current_thread_id"] = None
if "current_thread_name" not in st.session_state:
    st.session_state["current_thread_name"] = None
if "current_page" not in st.session_state:
    st.session_state["current_page"] = "thread"  # "thread" or "banned_links"
if "telemetry_buffer" not in st.session_state:
    st.session_state["telemetry_buffer"] = TelemetryBuffer()
if "scan_job_running" not in st.session_state:
    st.session_state["scan_job_running"] = False
if "scan_worker_thread" not in st.session_state:
    st.session_state["scan_worker_thread"] = None
if "scan_job_result" not in st.session_state:
    st.session_state["scan_job_result"] = []
if "scan_job_error" not in st.session_state:
    st.session_state["scan_job_error"] = None
if "scan_progress_completed" not in st.session_state:
    st.session_state["scan_progress_completed"] = 0
if "scan_progress_total" not in st.session_state:
    st.session_state["scan_progress_total"] = 1
if "scan_progress_label" not in st.session_state:
    st.session_state["scan_progress_label"] = "Waiting"
if "attached_results" not in st.session_state:
    st.session_state["attached_results"] = []
if "intel_page" not in st.session_state:
    st.session_state["intel_page"] = 0
if "intel_page_size" not in st.session_state:
    st.session_state["intel_page_size"] = 20
if "scan_requested" not in st.session_state:
    st.session_state["scan_requested"] = False
if "scan_query" not in st.session_state:
    st.session_state["scan_query"] = ""
if "scan_error" not in st.session_state:
    st.session_state["scan_error"] = None

# ============================================================================
# CACHING HELPERS - These reduce database hits and improve performance
# ============================================================================

@st.cache_resource
def get_cached_es_client():
    """
    Cache the Elasticsearch client connection.
    
    @st.cache_resource = Keep this object alive for the entire session
    This prevents reconnecting to ES on every page interaction
    """
    return database.get_es_client()


@st.cache_data(ttl=30, show_spinner=False)
def get_cached_thread_data(thread_id):
    """
    Cache thread intelligence data.
    
    @st.cache_data with ttl=300 means:
    - Query database once, reuse results for 5 minutes
    - Automatically refreshes after 5 minutes
    - Reduces database load 50-100x
    """
    es_client = get_cached_es_client()
    return database.get_thread_data(es_client, thread_id)


@st.cache_data(ttl=30, show_spinner=False)
def get_cached_trusted_sources(thread_id):
    """
    Cache trusted sources list (rarely changes during a session).
    
    Updates once every 5 minutes unless user manually deletes/adds source
    """
    es_client = get_cached_es_client()
    return database.get_trusted_sources(es_client, thread_id)


@st.cache_data(ttl=30, show_spinner=False)
def get_cached_thread_keywords(thread_id):
    """
    Cache keywords list for this operation.
    
    Keywords don't change often, so 5-min cache is safe
    """
    es_client = get_cached_es_client()
    return database.get_thread_keywords(es_client, thread_id)


@st.cache_data(ttl=30, show_spinner=False)
def get_cached_all_threads():
    """
    Cache all operations list.
    
    ttl=60 = refresh every minute (faster for seeing new operations)
    """
    es_client = get_cached_es_client()
    threads = database.get_all_threads(es_client)
    return threads if threads else []


def resolve_trust_status(update):
    """Resolve a result row into the binary Trusted/Untrusted model."""
    status = update.get("trust_status")
    if status in {"Trusted", "Untrusted"}:
        return status
    return "Trusted" if update.get("is_trusted") else "Untrusted"


def build_trusted_lookup(trusted_sources):
    """Build a fast lookup set of trusted URLs for scan normalization."""
    return {
        str(source.get("url", "")).strip().lower()
        for source in trusted_sources or []
        if str(source.get("url", "")).strip()
    }


def append_attached_results(new_results):
    """Append normalized scan results into session state without duplicating URLs."""
    existing = list(st.session_state.get("attached_results", []))
    seen = {item.get("onion_url") for item in existing if item.get("onion_url")}
    for item in new_results or []:
        url = item.get("onion_url")
        if url and url not in seen:
            existing.append(item)
            seen.add(url)
    st.session_state["attached_results"] = existing[-10:]
    return st.session_state["attached_results"]


def clear_dashboard_caches():
    """Invalidate cached data after writes so UI reflects the latest state."""
    get_cached_thread_data.clear()
    get_cached_trusted_sources.clear()
    get_cached_thread_keywords.clear()
    get_cached_all_threads.clear()


def initialize_scan_state():
    """Ensure the scan workflow has thread-safe state buckets for progress and telemetry."""
    st.session_state.setdefault("scan_job_running", False)
    st.session_state.setdefault("scan_job_result", [])
    st.session_state.setdefault("scan_job_error", None)
    st.session_state.setdefault("scan_progress_completed", 0)
    st.session_state.setdefault("scan_progress_total", 1)
    st.session_state.setdefault("scan_progress_label", "Waiting")
    st.session_state.setdefault("scan_progress_status", "Waiting")
    st.session_state.setdefault("scan_progress_detail", "")
    st.session_state.setdefault("scan_engine_statuses", {})
    st.session_state.setdefault("scan_last_summary", "")
    st.session_state.setdefault("attached_results", [])
    st.session_state.setdefault("telemetry_buffer", TelemetryBuffer())
    st.session_state.setdefault("scan_worker_thread", None)
    st.session_state.setdefault("scan_requested", False)
    st.session_state.setdefault("scan_query", "")
    st.session_state.setdefault("scan_error", None)

ctx = get_script_run_ctx()


def update_scan_progress(completed, total, engine_name, status="Completed", detail="", payload_bytes=0, latency_ms=0.0):
    """Publish progress updates from worker threads into Streamlit session state safely."""
    if ctx:
        add_script_run_ctx(threading.current_thread(), ctx)
        completed = int(completed)
        total = max(int(total), 1)
        engine_name = str(engine_name or "engine")
    statuses = dict(st.session_state.get("scan_engine_statuses", {}) or {})
    statuses[engine_name] = {
        "status": status,
        "detail": detail or "",
        "payload_bytes": int(payload_bytes or 0),
        "latency_ms": float(latency_ms or 0.0),
    }
    
    st.session_state["scan_progress_completed"] = completed
    st.session_state["scan_progress_total"] = total
    st.session_state["scan_progress_label"] = engine_name
    st.session_state["scan_progress_status"] = status
    st.session_state["scan_progress_detail"] = detail or ""
    st.session_state["scan_engine_statuses"] = statuses


def render_scan_status_panel():
    """Render the live scan progress bar and engine status matrix."""
    completed = st.session_state.get("scan_progress_completed", 0)
    total = max(st.session_state.get("scan_progress_total", 1), 1)
    progress_value = min(completed / total, 1.0)
    detail = st.session_state.get("scan_progress_detail", "")
    current_engine = st.session_state.get("scan_progress_label", "Waiting")

    with st.container():
        st.progress(progress_value)
        st.caption(f"Progress: {completed}/{total} engines completed ({progress_value:.1%})")
        st.caption(f"Current engine: {current_engine}")
        if detail:
            st.caption(detail)

        engine_statuses = st.session_state.get("scan_engine_statuses", {}) or {}
        if engine_statuses:
            st.write("### Engine Matrix")
            for engine, meta in list(engine_statuses.items())[-8:]:
                icon = "✅" if meta.get("status") == "Completed" else "❌" if meta.get("status") == "Failed" else "⏳"
                detail_text = meta.get("detail") or "Waiting"
                st.write(f"{icon} {engine}: {meta.get('status', 'Pending')} — {detail_text}")
        else:
            st.info("Waiting for the first engine response...")

    if st.session_state.get("scan_job_error"):
        st.error(f"⚠️ Scan interrupted: {st.session_state['scan_job_error']}")
    elif st.session_state.get("scan_job_result"):
        st.success(f"✅ Search complete! Found {len(st.session_state['scan_job_result'])} unique leads")


@st.fragment
def render_scan_progress_fragment():
    """Refresh the scan UI without re-entering the full app loop on every progress tick."""
    if not st.session_state.get("scan_job_running"):
        return

    render_scan_status_panel()
    if st.session_state.get("scan_worker_thread") and st.session_state["scan_worker_thread"].is_alive():
        time.sleep(0.2)
        st.rerun()


initialize_scan_state()


# --- Title & Header ---
st.title("🕵️‍♂️ Shadowpulse: Thread Intel")
st.write(f" Current Thread ID is: {st.session_state.get('current_thread_id', 'None')}")  
st.markdown("### Dark Web Threat Intelligence Scanner")
st.divider()

# --- Helper: Multithreaded Link Status Checker ---
def check_link_status_concurrent(updates, es_client, thread_id, max_workers=10, progress_callback=None, telemetry_callback=None):
    """
    Check the HTTP status of multiple onion links concurrently using ThreadPoolExecutor.
    
    This function performs simultaneous HTTP HEAD requests to multiple onion URLs,
    checking if they are online and responsive. Instead of pinging links one-at-a-time
    (which would freeze the Streamlit UI and take 25+ minutes for 100 links),
    this function pings up to max_workers links in parallel.
    
    For each URL, the function:
    1. Makes a HEAD request (smaller than GET, just checks status without downloading content)
    2. Records the HTTP status code (200=OK, 404=Not Found, 500=Server Error, etc.)
    3. Updates Elasticsearch immediately with the new status
    4. Moves to the next URL
    5. Calls progress_callback (if provided) to update UI in real-time
    
    The function is thread-safe and doesn't freeze the UI because the actual
    threading happens in the ThreadPoolExecutor context, separate from Streamlit's
    main event loop.
    
    Args:
        updates (list): List of update dictionaries, each containing 'onion_url' key
        es_client: Elasticsearch client instance (for database updates)
        thread_id (str): Current operation/thread ID (for database queries)
        max_workers (int): Maximum concurrent threads. Defaults to 10.
                          This means up to 10 Tor circuits will be used simultaneously.
        progress_callback (function): Optional callback function that accepts 
                                     (completed_count, total_links, url, status_code)
                                     for real-time progress tracking.
    
    Returns:
        list: List of tuples: [(url, status_code), ...]
              Example: [('http://site1.onion', 200), ('http://site2.onion', 500)]
    """
    results = []
    total_links = len(updates)
    completed_count = 0
    # Lock for thread-safe list appends and counter updates
    results_lock = threading.Lock()
    
    def ping_single_url(update):
        """
        Ping a single URL and record its HTTP status code.
        
        This function is executed in a thread pool and handles a single URL.
        It attempts a HEAD request and gracefully handles timeouts/errors by
        recording a 500 status code (server error).
        
        Args:
            update (dict): Dictionary containing 'onion_url' key
        
        Returns:
            tuple: (url, status_code)
        """
        url = update.get('onion_url')
        try:
            # Use optimized make_request with strict 15-second timeout.
            # HEAD request is used instead of GET to avoid downloading full page content,
            # which would be wasteful when we only need to check if the server is alive.
            response = tor_network.make_request(
                url,
                method='HEAD',
                timeout=15,
                telemetry_callback=telemetry_callback,
                engine_name=url,
            )
            code = response.status_code if response else 500
        except Exception as e:
            print(f"[Status Check] Error on {url}: {e}")
            code = 500  # Treat errors as server error (500)
        
        # Thread-safe database update: each thread updates ES with the new status code
        try:
            database.update_link_status(es_client, thread_id, url, code)
        except Exception as e:
            print(f"[Status Check] DB error: {e}")
        
        return (url, code)
    
    # Create a thread pool and submit all URLs at once
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all URL checks immediately (they run in parallel).
        # Create a dict mapping futures to URLs for tracking results.
        futures = {
            executor.submit(ping_single_url, update): update.get('onion_url')
            for update in updates
        }
        
        # Process results as each future completes (as_completed returns them in order of completion)
        for future in as_completed(futures):
            try:
                # Wait up to 20 seconds for this future (includes ping_single_url's 15s timeout + overhead)
                result = future.result(timeout=20)
                url, code = result
                
            except Exception as e:
                print(f"[Status Check] Future error: {e}")
                url = "error"
                code = 500
            
            # Always increment completed count and call callback (whether success or error)
            with results_lock:
                completed_count += 1
                if code != 500 or url != "error":  # Only append successful results
                    results.append((url, code))
                
                # Call progress callback with clamped progress value (0.0 to 1.0)
                if progress_callback:
                    # Clamp progress_percent to max 1.0 to prevent Streamlit errors
                    clamped_percent = min(completed_count / total_links, 1.0)
                    progress_callback(completed_count, total_links, url, code)
    
    return results


# --- Sidebar---
st.sidebar.header("📡 Mission Control")
es_client = get_cached_es_client()  # Use cached ES client for performance

# DEBUG: Print session state
print(f"[DEBUG] current_page={st.session_state.get('current_page')}")
print(f"[DEBUG] current_thread_name={st.session_state.get('current_thread_name')}")
print(f"[DEBUG] current_thread_id={st.session_state.get('current_thread_id')}")
print(f"[DEBUG] es_client={es_client is not None}")
print(f"[DEBUG] Condition for keywords: page=='thread'={st.session_state.get('current_page') == 'thread'}, thread_name={bool(st.session_state.get('current_thread_name'))}")

with st.sidebar.form("create_thread_form"):
    new_thread_name = st.text_input("New Operation Name", placeholder="e.g. Op Red Sparrow")
    submitted = st.form_submit_button("Create Operation")
    
    if submitted:
        if not new_thread_name:
            st.error("❌ Name cannot be empty.")
        elif not es_client:
            st.error("❌ Database offline.")
        else:
            try:
                tid, tname = database.create_thread(es_client, new_thread_name)
                st.session_state["current_thread_id"] = tid
                st.session_state["current_thread_name"] = tname
                st.success(f"✅ Created: {tname}")
                st.rerun()
            except Exception as e:
                st.error(f"Error creating thread: {e}")

if es_client:
   st.sidebar.divider()
   threads = get_cached_all_threads()  # Cached for 1 minute
   if threads:
      options = {t['name']: t['id'] for t in threads}
      index = 0
      if st.session_state["current_thread_name"] in options:
           list_keys = list(options.keys())
           index = list_keys.index(st.session_state["current_thread_name"])
      selected_name = st.sidebar.selectbox("Active Operation", list(options.keys()), index=index)
      if st.sidebar.button("📂 Load Operation"):
           st.session_state["current_thread_id"]= options[selected_name]
           st.session_state["current_thread_name"]= selected_name
           st.session_state["current_page"] = "thread"
           st.rerun()

   st.sidebar.divider()
   
   # Banned Links Button
   if st.sidebar.button("🚫 Banned Links", width='stretch'):
       st.session_state["current_page"] = "banned_links"
       st.rerun()
   
   # Back to Thread Button (only shown if on banned_links page)
   if st.session_state["current_page"] == "banned_links":
       if st.sidebar.button("← Back to Operation", width='stretch'):
           st.session_state["current_page"] = "thread"
           st.rerun()
   
   st.sidebar.divider()
   st.sidebar.caption("System Status")
   if es_client: 
    st.sidebar.success("Database: Online 🟢")
   else:
    st.sidebar.error("Database: Offline ")
   if st.session_state.get("tor_initialized"):
        st.sidebar.success("Tor Proxy: Active 🟢")
   else:
    st.sidebar.error("Tor Proxy: Disabled ")

# --- KEYWORDS SECTION IN SIDEBAR (OUTSIDE es_client block) ---
print(f"[DEBUG KEYWORDS] About to check keywords section")
print(f"[DEBUG KEYWORDS] current_page == 'thread': {st.session_state['current_page'] == 'thread'}")
print(f"[DEBUG KEYWORDS] current_thread_name: '{st.session_state['current_thread_name']}'")
print(f"[DEBUG KEYWORDS] Both conditions: {st.session_state['current_page'] == 'thread' and st.session_state['current_thread_name']}")

if st.session_state["current_page"] == "thread" and st.session_state["current_thread_name"]:
   print(f"[DEBUG KEYWORDS] SHOWING KEYWORDS SECTION")
   st.sidebar.write("### 🏷️ Keywords")
   keywords = get_cached_thread_keywords(st.session_state["current_thread_id"])  # Cached for 5 minutes
   
   # Manual keyword input in sidebar
   new_keyword = st.sidebar.text_input("Add Keyword", placeholder="Type keyword...", key="sidebar_keyword_input")
   if st.sidebar.button("➕ Add", key="sidebar_add_keyword_btn", width='stretch'):
       if new_keyword.strip():
           if database.add_keyword_to_thread(es_client, st.session_state["current_thread_id"], new_keyword):
               st.sidebar.success(f"✅ Added '{new_keyword}'")
               st.rerun()
           else:
               st.sidebar.warning(f"⚠️ Already exists")
       else:
           st.sidebar.error("❌ Empty")
   
   # Display keywords in sidebar
   if keywords:
       st.sidebar.write(f"**{len(keywords)} keyword(s):**")
       for keyword in keywords:
           col1, col2 = st.sidebar.columns([3, 1])
           with col1:
               st.write(f"🔹 {keyword}")
           with col2:
               if st.button("🗑️", key=f"del_kw_sidebar_{keyword}", help="Delete"):
                   database.remove_keyword_from_thread(es_client, st.session_state["current_thread_id"], keyword)
                   st.rerun()
   else:
       st.sidebar.caption("No keywords yet.")


#__main screen___

# PAGE: THREAD INTELLIGENCE (Main Thread View)
if st.session_state["current_page"] == "thread" and st.session_state["current_thread_name"]:
    if hasattr(st, "fragment"):
        @st.fragment
        def render_thread_view():
            st.subheader(f"📡 Operation: {st.session_state['current_thread_name']}")
            st.caption(f"Case ID: {st.session_state['current_thread_id']}")

            st.divider()
            st.write("### ⭐ Trusted Sources")

            trusted_sources = get_cached_trusted_sources(st.session_state["current_thread_id"])

            with st.expander("➕ Add New Trusted Source"):
                col1, col2 = st.columns([2, 2])
                with col1:
                    st.text_input("Source URL", placeholder="https://example.onion", key="new_source_url")
                with col2:
                    st.text_input("Source Title", placeholder="E.g., Dark Web Forum", key="new_source_title")

                if st.button("✅ Add to Trusted List", key="add_trusted_btn"):
                    source_url = (st.session_state.get("new_source_url") or "").strip()
                    source_title = (st.session_state.get("new_source_title") or "").strip()
                    if source_url:
                        if database.add_trusted_source(
                            es_client,
                            st.session_state["current_thread_id"],
                            source_url,
                            source_title or "No title"
                        ):
                            clear_dashboard_caches()
                            st.session_state["new_source_url"] = ""
                            st.session_state["new_source_title"] = ""
                            st.toast(f"✅ Added '{source_url}' to the trusted list")
                            st.rerun()
                        else:
                            st.error("❌ Failed to add trusted source")
                    else:
                        st.error("❌ URL cannot be empty")

            if trusted_sources:
                for source in trusted_sources:
                    col1, col2, col3 = st.columns([3, 2, 1])
                    with col1:
                        st.write(f"🔗 **{source.get('url', 'Unknown')}**")
                    with col2:
                        new_title = st.text_input(
                            "Title",
                            value=source.get('title', 'No title'),
                            key=f"edit_title_{source['_id']}"
                        )
                        if new_title != source.get('title', 'No title'):
                            database.update_trusted_source(es_client, source['_id'], title=new_title)
                            clear_dashboard_caches()
                            st.rerun()
                    with col3:
                        st.write("✅ Trusted")
                        if st.button("🗑️", key=f"del_trusted_{source['_id']}", help="Delete"):
                            database.delete_trusted_source(es_client, source['_id'])
                            clear_dashboard_caches()
                            st.rerun()
            else:
                st.info("ℹ️ No trusted sources added yet. Add one above!")

            st.divider()

            col1, col2 = st.columns([3, 1])
            with col1:
                query = st.text_input("Add Intel (Search Term)", placeholder="Search keywords to add to this case...", key="intel_query")
            with col2:
                st.write("")
                st.write("")
                scan_btn = st.button("🔍 Scan & Attach", type="primary")

            if st.session_state.get("scan_job_running"):
                render_scan_progress_fragment()
                render_telemetry_panel(
                    st.session_state["telemetry_buffer"],
                    st.container().empty(),
                    st.container().empty(),
                )

                if st.session_state.get("scan_job_error"):
                    st.error(f"⚠️ Scan interrupted: {st.session_state['scan_job_error']}")
                elif st.session_state.get("scan_job_result"):
                    results = st.session_state["scan_job_result"]
                    for item in results:
                        database.save_intel_update(
                            es_client,
                            st.session_state["current_thread_id"],
                            item.get('onion_url', ''),
                            item.get('title', 'Untitled'),
                            item.get('summary', 'Meta search result (Pending Crawl)'),
                            tags=[query],
                            trust_status=item.get('trust_status', 'Untrusted'),
                        )
                    database.add_keyword_to_thread(es_client, st.session_state["current_thread_id"], query)
                    clear_dashboard_caches()
                    st.success(f"✅ Attached {len(results)} new leads to operation.")
                else:
                    st.warning("⚠️ No new intelligence found.")

            if scan_btn and query:
                    # --- 1. UI Placeholders (Ensures progress bar stays visible) ---
                    progress_container = st.container()
                    status_text = progress_container.empty()
                    progress_bar = progress_container.progress(0)
                    
                    # --- 2. Thread Context & Callbacks ---
                    ctx = get_script_run_ctx()

                    def update_scan_progress(completed_count, total_engines, engine_name, status, detail, latency, payload):
                        # Inject context into the ThreadPoolExecutor workers
                        if ctx: add_script_run_ctx(threading.current_thread(), ctx)
                        progress_percent = completed_count / total_engines if total_engines > 0 else 0
                        status_text.write(f"🔍 Searching... {engine_name} ({completed_count}/{total_engines} engines checked)")
                        progress_bar.progress(progress_percent)

                    def telemetry_callback(engine, phase, latency_ms, payload_bytes, status_icon, detail=""):
                        if ctx: add_script_run_ctx(threading.current_thread(), ctx)
                        if "telemetry_buffer" in st.session_state:
                            st.session_state["telemetry_buffer"].push({
                                "engine": engine,
                                "phase": phase,
                                "latency_ms": latency_ms,
                                "payload_bytes": payload_bytes,
                                "status_icon": status_icon,
                                "detail": detail,
                            })
                    
                    # --- 3. Trust List Preparation ---
                    trusted_sources = get_cached_trusted_sources(st.session_state["current_thread_id"])
                    trusted_lookup = build_trusted_lookup(trusted_sources)
                    
                    # --- 4. EXECUTE SCAN (No complicated background threads needed!) ---
                    with st.spinner("Executing parallel dark web search..."):
                        raw_results = search_engine.search_parallel(
                            query,
                            max_workers=8,
                            progress_callback=update_scan_progress,
                            telemetry_callback=telemetry_callback,
                        )
                    
                    # --- 5. ATTACH TO DATABASE ---
                    if raw_results:
                        normalized_results = []
                        for item in raw_results:
                            normalized = database.normalize_scan_result(item, trusted_lookup)
                            if normalized:
                                normalized_results.append(normalized)
                        
                        # 🚨 EXPLICITLY SAVE TO ELASTICSEARCH (Guarantees they attach!)
                        for item in normalized_results:
                            database.save_intel_update(
                                es_client, 
                                st.session_state["current_thread_id"], 
                                item.get('onion_url', ''),
                                item.get('title', 'Unknown Title'),
                                "Meta search result (Pending Crawl)", 
                                tags=[query]
                            )
                            
                        # If you had a custom UI attach function, safely attempt it
                        try:
                            append_attached_results(normalized_results)
                        except NameError:
                            pass
                        
                        progress_bar.progress(1.0)
                        status_text.success(f"✅ Search Complete! Successfully attached {len(normalized_results)} new links!")
                        
                        # PAUSE for 2 seconds so you can actually read the success message before it reloads!
                        time.sleep(2) 
                        st.rerun()
                    else:
                        progress_bar.progress(0)
                        status_text.warning("⚠️ No new intelligence found.")

            st.divider()
            st.write("### 📝 Intelligence Feed")

            updates = get_cached_thread_data(st.session_state["current_thread_id"])

            if st.session_state.get("attached_results"):
                with st.expander("🧾 Recently Attached Intel", expanded=False):
                    for item in st.session_state["attached_results"][-5:]:
                        st.write(f"• {item.get('title', 'Untitled')} — {item.get('onion_url', 'unknown')} ({item.get('trust_status', 'Untrusted')})")

            st.download_button(
                label="📦 Export STIX 2.1 Bundle",
                data=export_stix_bundle_json(
                    [
                        {
                            "onion_url": update.get("onion_url"),
                            "title": update.get("title", "Unknown"),
                            "source": update.get("source", "shadowpulse"),
                            "latency_ms": update.get("latency_ms", 0.0),
                            "http_status": update.get("last_status_code", 0),
                            "payload_bytes": update.get("payload_bytes", 0),
                            "crawled_at": update.get("scraped_at") or update.get("crawled_at") or datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "summary": update.get("summary", "No summary available"),
                            "trust_status": resolve_trust_status(update),
                        }
                        for update in updates if update.get("onion_url")
                    ],
                    thread_id=str(st.session_state.get("current_thread_id", "shadowpulse")),
                    thread_name=str(st.session_state.get("current_thread_name", "Shadowpulse")),
                    trusted_sources=[{"url": source.get("url"), "title": source.get("title")} for source in trusted_sources],
                ),
                file_name="shadowpulse_threat_intel_stix21.json",
                mime="application/json",
                disabled=not updates,
            )

            if updates:
                active_count = sum(1 for u in updates if u.get('last_status_code') == 200)
                dead_count = len(updates) - active_count
                stat_col1, stat_col2 = st.columns([1, 2])
                with stat_col1:
                    st.caption("Link Health Overview")
                    source = pd.DataFrame({
                        "Status": ["Active", "Down"],
                        "Count": [active_count, dead_count],
                        "Color": ["green", "red"]
                    })
                    base = alt.Chart(source).encode(theta=alt.Theta("Count", stack=True))
                    pie = base.mark_arc(outerRadius=80).encode(
                        color=alt.Color("Status", scale=alt.Scale(domain=["Active", "Down"], range=["green", "red"])),
                        tooltip=["Status", "Count"]
                    )
                    st.altair_chart(pie, width="stretch")

                with stat_col2:
                    st.write("")
                    if st.button("🔄 Check Link Status"):
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        results_text = st.empty()

                        def update_progress(completed, total, url, code):
                            progress_percent = min(completed / total, 1.0)
                            status_icon = "✅" if code == 200 else "❌"
                            url_display = url.split('/')[-1][:40] if url and url != "error" else ("error" if url == "error" else "unknown")
                            status_text.write(f"🔍 Pinging... **{url_display}** {status_icon} ({completed}/{total} checked)")
                            progress_bar.progress(progress_percent)

                        results = check_link_status_concurrent(
                            updates,
                            es_client,
                            st.session_state["current_thread_id"],
                            max_workers=10,
                            progress_callback=update_progress
                        )

                        alive = sum(1 for _, code in results if code == 200)
                        dead = len(results) - alive
                        progress_bar.progress(1.0)
                        status_text.success("✅ Status check complete!")
                        results_text.info(f"📊 Results: **{alive}** active 🟢 | **{dead}** down 🔴")
                        clear_dashboard_caches()
                        st.rerun()

                    if st.button("🗑️ Delete All Dead Links", key="delete_all_dead"):
                        dead_links = [u for u in updates if u.get('last_status_code') not in [200, 0]]
                        if dead_links:
                            for link in dead_links:
                                try:
                                    database.delete_intel_update(es_client, st.session_state["current_thread_id"], link.get('onion_url'))
                                except Exception as exc:
                                    print(f"Error deleting {link.get('onion_url')}: {exc}")
                            st.success(f"✅ Deleted {len(dead_links)} dead links")
                            clear_dashboard_caches()
                            st.rerun()
                        else:
                            st.info("ℹ️ No dead links to delete. All links are either active or untested.")

            if updates:
                total_pages = max(1, math.ceil(len(updates) / st.session_state["intel_page_size"]))
                page = min(st.session_state["intel_page"], total_pages - 1)
                visible_updates = updates[page * st.session_state["intel_page_size"]:(page + 1) * st.session_state["intel_page_size"]]
                nav_col1, nav_col2 = st.columns([1, 1])
                with nav_col1:
                    if st.button("⬅️ Prev", disabled=page <= 0):
                        st.session_state["intel_page"] = max(0, page - 1)
                        st.rerun()
                with nav_col2:
                    if st.button("Next ➡️", disabled=page >= total_pages - 1):
                        st.session_state["intel_page"] = min(total_pages - 1, page + 1)
                        st.rerun()
                st.caption(f"Showing page {page + 1} of {total_pages}")
                for update in visible_updates:
                    with st.container():
                        code = update.get('last_status_code', 0)
                        status_icon = "✅" if code == 200 else ("⚪" if code == 0 else "❌")
                        st.markdown(f"**{status_icon} 🔗 {update.get('title', 'Unknown Site')}**")
                        st.caption(f"Source: `{update.get('onion_url')}` | Tags: {update.get('tags', [])}")
                        summary = update.get('summary', 'No summary.')
                        st.info(summary)

                        c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 2])
                        with c1:
                            if st.button("🕷 Deep Crawl", key=f"btn_{update.get('onion_url')}"):
                                from src.core import crawler
                                with st.spinner("Accessing hidden service..."):
                                    content = crawler.fetch_onion_content(update.get('onion_url'))
                                    if content:
                                        database.save_intel_update(
                                            es_client,
                                            st.session_state["current_thread_id"],
                                            update.get('onion_url'),
                                            update.get('title'),
                                            content,
                                            tags=update.get('tags', []),
                                            last_status_code=200
                                        )
                                        clear_dashboard_caches()
                                        st.success("Extracted!")
                                        st.rerun()
                                    else:
                                        st.error("Site unreachable.")

                        with c2:
                            if st.button("⭐ Add to Trust", key=f"add_trust_{update.get('onion_url')}"):
                                url = update.get('onion_url')
                                title = update.get('title', 'No title')
                                if database.add_trusted_source(es_client, st.session_state["current_thread_id"], url, title=title):
                                    clear_dashboard_caches()
                                    st.toast(f"✅ Added '{url}' to the trusted list")
                                    st.rerun()
                                else:
                                    st.error("❌ Error adding to trust list")

                        with c3:
                            if st.button("🚫 Ban Local", key=f"ban_local_{update.get('onion_url')}"):
                                try:
                                    database.ban_link_locally(es_client, st.session_state["current_thread_id"], update.get('onion_url'))
                                    database.delete_intel_update(es_client, st.session_state["current_thread_id"], update.get('onion_url'))
                                    clear_dashboard_caches()
                                    st.success("✅ Locally banned & removed")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"❌ Error banning link: {exc}")

                        with c4:
                            if st.button("🛑 Ban Global", key=f"ban_global_{update.get('onion_url')}"):
                                try:
                                    database.ban_link_globally(es_client, update.get('onion_url'))
                                    deleted_count = database.delete_link_from_all_threads(es_client, update.get('onion_url'))
                                    clear_dashboard_caches()
                                    st.success(f"✅ Globally banned & removed from {deleted_count} thread(s)")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"❌ Error banning link: {exc}")

                        with c5:
                            with st.expander("View Raw Data"):
                                st.code(update.get('full_content'))

                        st.markdown("---")
            else:
                st.info("No intelligence gathered for this operation yet. Run a scan above.")

        render_thread_view()
    else:
        # Fallback for older Streamlit builds.
        st.subheader(f"📡 Operation: {st.session_state['current_thread_name']}")
        st.caption(f"Case ID: {st.session_state['current_thread_id']}")
        st.divider()
        st.write("### ⭐ Trusted Sources")
        trusted_sources = get_cached_trusted_sources(st.session_state["current_thread_id"])
        with st.expander("➕ Add New Trusted Source"):
            col1, col2 = st.columns([2, 2])
            with col1:
                new_source_url = st.text_input("Source URL", placeholder="https://example.onion", key="new_source_url")
            with col2:
                new_source_title = st.text_input("Source Title", placeholder="E.g., Dark Web Forum", key="new_source_title")
            if st.button("✅ Add to Trusted List", key="add_trusted_btn"):
                source_url = (st.session_state.get("new_source_url") or "").strip()
                source_title = (st.session_state.get("new_source_title") or "").strip()
                if source_url:
                    if database.add_trusted_source(es_client, st.session_state["current_thread_id"], source_url, source_title or "No title"):
                        clear_dashboard_caches()
                        st.session_state["new_source_url"] = ""
                        st.session_state["new_source_title"] = ""
                        st.toast(f"✅ Added '{source_url}' to the trusted list")
                        st.rerun()
                    else:
                        st.error("❌ Failed to add trusted source")
                else:
                    st.error("❌ URL cannot be empty")
        if trusted_sources:
            for source in trusted_sources:
                col1, col2, col3 = st.columns([3, 2, 1])
                with col1:
                    st.write(f"🔗 **{source.get('url', 'Unknown')}**")
                with col2:
                    new_title = st.text_input("Title", value=source.get('title', 'No title'), key=f"edit_title_{source['_id']}")
                    if new_title != source.get('title', 'No title'):
                        database.update_trusted_source(es_client, source['_id'], title=new_title)
                        clear_dashboard_caches()
                        st.rerun()
                with col3:
                    st.write("✅ Trusted")
                    if st.button("🗑️", key=f"del_trusted_{source['_id']}", help="Delete"):
                        database.delete_trusted_source(es_client, source['_id'])
                        clear_dashboard_caches()
                        st.rerun()
        else:
            st.info("ℹ️ No trusted sources added yet. Add one above!")
        st.divider()
        col1, col2 = st.columns([3, 1])
        with col1:
            query = st.text_input("Add Intel (Search Term)", placeholder="Search keywords to add to this case...", key="intel_query")
        with col2:
            st.write("")
            st.write("")
            scan_btn = st.button("🔍 Scan & Attach", type="primary")
        if st.session_state.get("scan_job_running"):
            render_scan_progress_fragment()
            render_telemetry_panel(st.session_state["telemetry_buffer"], st.container().empty(), st.container().empty())
            if st.session_state.get("scan_job_error"):
                st.error(f"⚠️ Scan interrupted: {st.session_state['scan_job_error']}")
            elif st.session_state.get("scan_job_result"):
                results = st.session_state["scan_job_result"]
                for item in results:
                    database.save_intel_update(es_client, st.session_state["current_thread_id"], item.get('onion_url', ''), item.get('title', 'Untitled'), item.get('summary', 'Meta search result (Pending Crawl)'), tags=[query], trust_status=item.get('trust_status', 'Untrusted'))
                database.add_keyword_to_thread(es_client, st.session_state["current_thread_id"], query)
                clear_dashboard_caches()
                st.success(f"✅ Attached {len(results)} new leads to operation.")
            else:
                st.warning("⚠️ No new intelligence found.")
        if scan_btn and query:
            if st.session_state.get("scan_job_running"):
                st.warning("A scan is already running. Please wait for it to finish.")
            else:
                st.session_state["scan_job_running"] = True
                st.session_state["scan_job_error"] = None
                st.session_state["scan_job_result"] = []
                st.session_state["scan_progress_completed"] = 0
                st.session_state["scan_progress_total"] = len(config.SEARCH_ENGINES or []) or 1
                st.session_state["scan_progress_label"] = "Bootstrapping"
                st.session_state["scan_progress_status"] = "Queued"
                st.session_state["scan_progress_detail"] = "Preparing engines"
                st.session_state["scan_engine_statuses"] = {}
                st.session_state["telemetry_buffer"].clear()
                def update_progress(completed, total, engine_url, status="Completed", detail="", payload_bytes=0, latency_ms=0.0):
                    st.session_state["scan_progress_completed"] = int(completed)
                    st.session_state["scan_progress_total"] = max(int(total), 1)
                    engine_name = str(engine_url or "engine")
                    st.session_state["scan_progress_label"] = engine_name
                    st.session_state["scan_progress_status"] = status
                    st.session_state["scan_progress_detail"] = detail or ""
                    statuses = dict(st.session_state.get("scan_engine_statuses", {}) or {})
                    statuses[engine_name] = {"status": status, "detail": detail or "", "payload_bytes": int(payload_bytes or 0), "latency_ms": float(latency_ms or 0.0)}
                    st.session_state["scan_engine_statuses"] = statuses
                def telemetry_callback(engine, phase, latency_ms, payload_bytes, status_icon, detail=""):
                    st.session_state["telemetry_buffer"].push({"engine": engine, "phase": phase, "latency_ms": latency_ms, "payload_bytes": payload_bytes, "status_icon": status_icon, "detail": detail})
                trusted_sources = get_cached_trusted_sources(st.session_state["current_thread_id"])
                trusted_lookup = build_trusted_lookup(trusted_sources)
                def run_scan_worker():
                    try:
                        raw_results = search_engine.search_parallel(query, max_workers=min(8, max(2, len(config.SEARCH_ENGINES or []))), progress_callback=update_progress, telemetry_callback=telemetry_callback)
                        normalized_results = []
                        for item in raw_results or []:
                            normalized = database.normalize_scan_result(item, trusted_lookup)
                            if normalized:
                                normalized_results.append(normalized)
                        st.session_state["scan_job_result"] = normalized_results
                        append_attached_results(normalized_results)
                    except Exception as exc:
                        st.session_state["scan_job_error"] = str(exc)
                        st.session_state["scan_job_result"] = []
                    finally:
                        st.session_state["scan_job_running"] = False
                        st.session_state["scan_progress_status"] = "Completed" if not st.session_state.get("scan_job_error") else "Failed"
                        st.session_state["scan_progress_detail"] = "Scan cycle complete"
                        st.session_state["scan_pending_completion"] = True
                worker = threading.Thread(target=run_scan_worker, daemon=True)
                st.session_state["scan_worker_thread"] = worker
                worker.start()
                st.rerun()
        st.divider()
        st.write("### 📝 Intelligence Feed")
        updates = get_cached_thread_data(st.session_state["current_thread_id"])
        if st.session_state.get("attached_results"):
            with st.expander("🧾 Recently Attached Intel", expanded=False):
                for item in st.session_state["attached_results"][-5:]:
                    st.write(f"• {item.get('title', 'Untitled')} — {item.get('onion_url', 'unknown')} ({item.get('trust_status', 'Untrusted')})")
        st.download_button(label="📦 Export STIX 2.1 Bundle", data=export_stix_bundle_json([{"onion_url": update.get("onion_url"), "title": update.get("title", "Unknown"), "source": update.get("source", "shadowpulse"), "latency_ms": update.get("latency_ms", 0.0), "http_status": update.get("last_status_code", 0), "payload_bytes": update.get("payload_bytes", 0), "crawled_at": update.get("scraped_at") or update.get("crawled_at") or datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"), "summary": update.get("summary", "No summary available"), "trust_status": resolve_trust_status(update)} for update in updates if update.get("onion_url")], thread_id=str(st.session_state.get("current_thread_id", "shadowpulse")), thread_name=str(st.session_state.get("current_thread_name", "Shadowpulse")), trusted_sources=[{"url": source.get("url"), "title": source.get("title")} for source in trusted_sources]), file_name="shadowpulse_threat_intel_stix21.json", mime="application/json", disabled=not updates)
        if updates:
            active_count = sum(1 for u in updates if u.get('last_status_code') == 200)
            dead_count = len(updates) - active_count
            stat_col1, stat_col2 = st.columns([1, 2])
            with stat_col1:
                st.caption("Link Health Overview")
                source = pd.DataFrame({"Status": ["Active", "Down"], "Count": [active_count, dead_count], "Color": ["green", "red"]})
                base = alt.Chart(source).encode(theta=alt.Theta("Count", stack=True))
                pie = base.mark_arc(outerRadius=80).encode(color=alt.Color("Status", scale=alt.Scale(domain=["Active", "Down"], range=["green", "red"])), tooltip=["Status", "Count"])
                st.altair_chart(pie, width="stretch")
            with stat_col2:
                st.write("")
                if st.button("🔄 Check Link Status"):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    results_text = st.empty()
                    def update_progress(completed, total, url, code):
                        progress_percent = min(completed / total, 1.0)
                        status_icon = "✅" if code == 200 else "❌"
                        url_display = url.split('/')[-1][:40] if url and url != "error" else ("error" if url == "error" else "unknown")
                        status_text.write(f"🔍 Pinging... **{url_display}** {status_icon} ({completed}/{total} checked)")
                        progress_bar.progress(progress_percent)
                    results = check_link_status_concurrent(updates, es_client, st.session_state["current_thread_id"], max_workers=10, progress_callback=update_progress)
                    alive = sum(1 for _, code in results if code == 200)
                    dead = len(results) - alive
                    progress_bar.progress(1.0)
                    status_text.success("✅ Status check complete!")
                    results_text.info(f"📊 Results: **{alive}** active 🟢 | **{dead}** down 🔴")
                    clear_dashboard_caches()
                    st.rerun()
                if st.button("🗑️ Delete All Dead Links", key="delete_all_dead"):
                    dead_links = [u for u in updates if u.get('last_status_code') not in [200, 0]]
                    if dead_links:
                        for link in dead_links:
                            try:
                                database.delete_intel_update(es_client, st.session_state["current_thread_id"], link.get('onion_url'))
                            except Exception as exc:
                                print(f"Error deleting {link.get('onion_url')}: {exc}")
                        st.success(f"✅ Deleted {len(dead_links)} dead links")
                        clear_dashboard_caches()
                        st.rerun()
                    else:
                        st.info("ℹ️ No dead links to delete. All links are either active or untested.")
        if updates:
            page = min(st.session_state["intel_page"], max(0, math.ceil(len(updates) / st.session_state["intel_page_size"]) - 1))
            visible_updates = updates[page * st.session_state["intel_page_size"]:(page + 1) * st.session_state["intel_page_size"]]
            nav_col1, nav_col2 = st.columns([1, 1])
            with nav_col1:
                if st.button("⬅️ Prev", disabled=page <= 0):
                    st.session_state["intel_page"] = max(0, page - 1)
                    st.rerun()
            with nav_col2:
                if st.button("Next ➡️", disabled=page >= max(0, math.ceil(len(updates) / st.session_state["intel_page_size"]) - 1)):
                    st.session_state["intel_page"] = min(max(0, math.ceil(len(updates) / st.session_state["intel_page_size"]) - 1), page + 1)
                    st.rerun()
            st.caption(f"Showing page {page + 1} of {max(1, math.ceil(len(updates) / st.session_state['intel_page_size']))}")
            for update in visible_updates:
                with st.container():
                    code = update.get('last_status_code', 0)
                    status_icon = "✅" if code == 200 else ("⚪" if code == 0 else "❌")
                    st.markdown(f"**{status_icon} 🔗 {update.get('title', 'Unknown Site')}**")
                    st.caption(f"Source: `{update.get('onion_url')}` | Tags: {update.get('tags', [])}")
                    summary = update.get('summary', 'No summary.')
                    st.info(summary)
                    c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 2])
                    with c1:
                        if st.button("🕷 Deep Crawl", key=f"btn_{update.get('onion_url')}"):
                            from src.core import crawler
                            with st.spinner("Accessing hidden service..."):
                                content = crawler.fetch_onion_content(update.get('onion_url'))
                                if content:
                                    database.save_intel_update(es_client, st.session_state["current_thread_id"], update.get('onion_url'), update.get('title'), content, tags=update.get('tags', []), last_status_code=200)
                                    clear_dashboard_caches()
                                    st.success("Extracted!")
                                    st.rerun()
                                else:
                                    st.error("Site unreachable.")
                    with c2:
                        if st.button("⭐ Add to Trust", key=f"add_trust_{update.get('onion_url')}"):
                            url = update.get('onion_url')
                            title = update.get('title', 'No title')
                            if database.add_trusted_source(es_client, st.session_state["current_thread_id"], url, title=title):
                                clear_dashboard_caches()
                                st.toast(f"✅ Added '{url}' to the trusted list")
                                st.rerun()
                            else:
                                st.error("❌ Error adding to trust list")
                    with c3:
                        if st.button("🚫 Ban Local", key=f"ban_local_{update.get('onion_url')}"):
                            try:
                                database.ban_link_locally(es_client, st.session_state["current_thread_id"], update.get('onion_url'))
                                database.delete_intel_update(es_client, st.session_state["current_thread_id"], update.get('onion_url'))
                                clear_dashboard_caches()
                                st.success("✅ Locally banned & removed")
                                st.rerun()
                            except Exception as exc:
                                st.error(f"❌ Error banning link: {exc}")
                    with c4:
                        if st.button("🛑 Ban Global", key=f"ban_global_{update.get('onion_url')}"):
                            try:
                                database.ban_link_globally(es_client, update.get('onion_url'))
                                deleted_count = database.delete_link_from_all_threads(es_client, update.get('onion_url'))
                                clear_dashboard_caches()
                                st.success(f"✅ Globally banned & removed from {deleted_count} thread(s)")
                                st.rerun()
                            except Exception as exc:
                                st.error(f"❌ Error banning link: {exc}")
                    with c5:
                        with st.expander("View Raw Data"):
                            st.code(update.get('full_content'))
                    st.markdown("---")
        else:
            st.info("No intelligence gathered for this operation yet. Run a scan above.")

# PAGE: BANNED LINKS MANAGEMENT
elif st.session_state["current_page"] == "banned_links":
    st.title("🚫 Banned Links Management")
    st.write("View and manage locally and globally banned links.")
    st.divider()
    
    if not es_client:
        st.error("❌ Database offline. Cannot access banned links.")
    else:
        # Get current thread ID and all banned links
        thread_id = st.session_state["current_thread_id"]
        
        # Create tabs for Local and Global bans
        tab1, tab2 = st.tabs(["Local Bans (This Thread)", "Global Bans (All Threads)"])
        
        # --- TAB 1: LOCAL BANS ---
        with tab1:
            if thread_id:
                local_bans = database.get_local_banned_links(es_client, thread_id)
                
                if local_bans:
                    st.write(f"**{len(local_bans)} locally banned link(s)** in this operation")
                    st.divider()
                    
                    for ban in local_bans:
                        url = ban.get('banned_url')
                        banned_at = ban.get('banned_at', 'Unknown')
                        
                        col1, col2 = st.columns([5, 1])
                        with col1:
                            st.markdown(f"🔗 **{url}**")
                            st.caption(f"Banned at: {banned_at}")
                        
                        with col2:
                            if st.button("↩️ Unban", key=f"unban_local_{url}"):
                                try:
                                    database.unban_link_locally(es_client, thread_id, url)
                                    st.success(f"✅ Unbanned! Link will show up in future scans.")
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Error unbanning: {e}")
                        
                        st.divider()
                else:
                    st.info("ℹ️ No locally banned links in this operation.")
            else:
                st.warning("⚠️ Please select an operation first to view local bans.")
        
        # --- TAB 2: GLOBAL BANS ---
        with tab2:
            global_bans = database.get_global_banned_links(es_client)
            
            if global_bans:
                st.write(f"**{len(global_bans)} globally banned link(s)** across all operations")
                st.divider()
                
                for ban in global_bans:
                    url = ban.get('banned_url')
                    banned_at = ban.get('banned_at', 'Unknown')
                    
                    col1, col2 = st.columns([5, 1])
                    with col1:
                        st.markdown(f"🔗 **{url}**")
                        st.caption(f"Banned at: {banned_at}")
                    
                    with col2:
                        if st.button("↩️ Unban", key=f"unban_global_{url}"):
                            try:
                                database.unban_link_globally(es_client, url)
                                st.success(f"✅ Unbanned! Link will show up in future scans.")
                                time.sleep(1)
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Error unbanning: {e}")
                    
                    st.divider()
            else:
                st.info("ℹ️ No globally banned links.")

else:
    # --- WELCOME SCREEN (No Thread Selected or on Welcome) ---
    st.write("## 👋 Welcome, Analyst.")
    st.info("👈 Please Select or Create an Operation in the sidebar to begin.")
    
    # --- GLOBAL STATS CHART (Native Bar Chart) ---
    st.divider()
    st.subheader("📊 Global Operation Statistics")
    
    if es_client:
        stats = database.get_dashboard_stats(es_client)
        if stats:
            # Prepare data for native st.bar_chart
            df_stats = pd.DataFrame(stats)
            df_stats = df_stats.set_index("name") # Set name as index for labels
            
            st.write("Top Operations by Active Links:")
            # Simple native bar chart
            st.bar_chart(df_stats['count']) 
        else:
            st.caption("No active links found in database yet.")

    st.markdown("""
    **How to use:**
    1. **Create an Operation** (e.g., "Ransomware Group X")
    2. **Scan for keywords** to populate the thread.
    3. **Deep Crawl** specific links to extract full text.
    """)


#Benefits of ThreadPoolExecutor:
#Thread Reuse: Instead of creating/destroying threads for each task, it reuses them (like a "pool")

#Resource Management: Limits concurrent threads (prevents system overload)

#Error Handling: Better exception propagation

#Timeout Support: future.result(timeout=20)

#Clean Shutdown: with block ensures threads are cleaned up
