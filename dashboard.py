# dashboard.py
import streamlit as st
import pandas as pd
import altair as alt  # Built-in with Streamlit
from datetime import datetime
import time  
import config
import database
import search_engine
import tor_network
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

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

# --- Title & Header ---
st.title("🕵️‍♂️ Shadowpulse: Thread Intel")
st.write(f"🔴 DEBUG: Current Thread ID is: {st.session_state.get('current_thread_id', 'None')}")  # <--- ADD THIS
st.markdown("### Dark Web Threat Intelligence Scanner")
st.divider()

# --- Helper: Multithreaded Link Status Checker ---
def check_link_status_concurrent(updates, es_client, thread_id, max_workers=10):
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
    
    The function is thread-safe and doesn't freeze the UI because the actual
    threading happens in the ThreadPoolExecutor context, separate from Streamlit's
    main event loop.
    
    Args:
        updates (list): List of update dictionaries, each containing 'onion_url' key
        es_client: Elasticsearch client instance (for database updates)
        thread_id (str): Current operation/thread ID (for database queries)
        max_workers (int): Maximum concurrent threads. Defaults to 10.
                          This means up to 10 Tor circuits will be used simultaneously.
    
    Returns:
        list: List of tuples: [(url, status_code), ...]
              Example: [('http://site1.onion', 200), ('http://site2.onion', 500)]
    """
    results = []
    # Lock for thread-safe list appends (though Python list.append is atomic anyway)
    results_lock = threading.Lock() #threading.lock : one append at a time
    
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
            response = tor_network.make_request(url, method='HEAD', timeout=15)
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
                with results_lock: #unnecessary defensive programming : forloop does not work simultaneously
                    results.append(result)
            except Exception as e:
                print(f"[Status Check] Future error: {e}")
    
    return results


# --- Sidebar---
st.sidebar.header("📡 Mission Control")
es_client = database.get_es_client()

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
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Error creating thread: {e}")

if es_client:
   st.sidebar.divider()
   threads = database.get_all_threads(es_client)
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


#__main screen___

if st.session_state["current_thread_name"]:
    st.subheader(f"📡 Operation: {st.session_state['current_thread_name']}")
    st.caption(f"Case ID: {st.session_state['current_thread_id']}")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        query = st.text_input("Add Intel (Search Term)", placeholder="Search keywords to add to this case...")
    with col2:
        st.write("")
        st.write("")
        scan_btn = st.button("🔍 Scan & Attach", type="primary")
    
    if scan_btn and query:  
      with st.spinner(f"Searching dark web for '{query}'..."):
         results = search_engine.search_parallel(query, max_workers=8)

         if results:
             for item in results:
                database.save_intel_update(
                        es_client, 
                        st.session_state["current_thread_id"], 
                        item['onion_url'],
                        item['title'],
                        "Meta search result (Pending Crawl)", 
                        tags=[query]
                    )
             st.success(f"✅ Attached {len(results)} new leads to operation.")
             time.sleep(1)
             st.rerun()
         else:
             st.warning("No new intelligence found.")

    st.divider()
    st.write("### 📝 Intelligence Feed")

    updates = database.get_thread_data(es_client , st.session_state["current_thread_id"])
    
    # --- STATISTICS SECTION (NATIVE CHARTS) --- 
    if updates:
        active_count = sum(1 for u in updates if u.get('last_status_code') == 200)
        dead_count = len(updates) - active_count
        
        stat_col1, stat_col2 = st.columns([1, 2])
        
        with stat_col1:
             st.caption("Link Health Overview")
             # Create simple dataframe for chart
             source = pd.DataFrame({
                 "Status": ["Active", "Down"],
                 "Count": [active_count, dead_count],
                 "Color": ["green", "red"] 
             })
             
             # Altair Pie Chart (Built-in to Streamlit)
             base = alt.Chart(source).encode(
                theta=alt.Theta("Count", stack=True)
             )
             pie = base.mark_arc(outerRadius=80).encode(
                color=alt.Color("Status", scale=alt.Scale(domain=["Active", "Down"], range=["green", "red"])),
                tooltip=["Status", "Count"]
             )
             st.altair_chart(pie, use_container_width=True)

        with stat_col2:
            st.write("")
            if st.button("🔄 Check Link Status (Ping All)"):
                progress_container = st.empty()
                status_text = st.empty()
                
                # Run concurrent status check
                with st.spinner("🔍 Checking status of all links in parallel..."):
                    results = check_link_status_concurrent(
                        updates, 
                        es_client, 
                        st.session_state["current_thread_id"],
                        max_workers=10
                    )
                
                # Show summary
                alive = sum(1 for _, code in results if code == 200)
                dead = len(results) - alive
                
                st.success(f"✅ Status check complete! {alive} active, {dead} down.")
                time.sleep(1)
                st.rerun()

    if updates :
        for update in updates:
           with st.container():
                # Status Tick Logic 
                code = update.get('last_status_code', 0)
                if code == 200:
                    status_icon = "✅" # Green Tick
                elif code == 0:
                    status_icon = "⚪" # Grey circle (Unknown)
                else:
                    status_icon = "❌" # Red Cross

                st.markdown(f"**{status_icon} 🔗 {update.get('title', 'Unknown Site')}**")
                st.caption(f"Source: `{update.get('onion_url')}` | Tags: {update.get('tags', [])}")
                
                summary = update.get('summary', 'No summary.')
                st.info(summary)
                
                c1, c2 = st.columns([1, 4])
                with c1:
                    if st.button("🕷 Deep Crawl", key=f"btn_{update.get('onion_url')}"):
                        import crawler
                        with st.spinner("Accessing hidden service..."):
                            content = crawler.fetch_onion_content(update.get('onion_url'))
                            if content:
                                    database.save_intel_update(
                                    es_client,
                                    st.session_state["current_thread_id"],
                                    update.get('onion_url'),
                                    update.get('title'),
                                    content,
                                    tags=update.get('tags', [])
                                )
                                    st.success("Extracted!")
                                    st.rerun()
                            else:
                                st.error("Site unreachable.")
                with c2:
                    with st.expander("View Raw Data"):
                        st.code(update.get('full_content'))
                
                st.markdown("---")
    else:
       st.info("No intelligence gathered for this operation yet. Run a scan above.")
else:
    # --- WELCOME SCREEN (No Thread Selected) ---
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