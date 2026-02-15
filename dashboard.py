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
if "current_page" not in st.session_state:
    st.session_state["current_page"] = "thread"  # "thread" or "banned_links"

# --- Title & Header ---
st.title("🕵️‍♂️ Shadowpulse: Thread Intel")
st.write(f"🔴 DEBUG: Current Thread ID is: {st.session_state.get('current_thread_id', 'None')}")  # <--- ADD THIS
st.markdown("### Dark Web Threat Intelligence Scanner")
st.divider()

# --- Helper: Multithreaded Link Status Checker ---
def check_link_status_concurrent(updates, es_client, thread_id, max_workers=10, progress_callback=None):
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
           st.session_state["current_page"] = "thread"
           st.rerun()

   st.sidebar.divider()
   
   # Banned Links Button
   if st.sidebar.button("🚫 Banned Links", use_container_width=True):
       st.session_state["current_page"] = "banned_links"
       st.rerun()
   
   # Back to Thread Button (only shown if on banned_links page)
   if st.session_state["current_page"] == "banned_links":
       if st.sidebar.button("← Back to Operation", use_container_width=True):
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


#__main screen___

# PAGE: THREAD INTELLIGENCE (Main Thread View)
if st.session_state["current_page"] == "thread" and st.session_state["current_thread_name"]:
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
      # Create containers for progress display
      progress_container = st.container()
      progress_bar = progress_container.progress(0)
      status_text = progress_container.empty()
      results_placeholder = progress_container.empty()
      
      def update_progress(completed, total, engine_url):
          """Callback function to update progress bar in real-time"""
          progress_percent = completed / total
          engine_name = engine_url.split('/')[2] if '/' in engine_url else engine_url
          status_text.write(f"🔍 Searching... **{engine_name}** ✓ ({completed}/{total} engines)")
          progress_bar.progress(progress_percent)
      
      results = search_engine.search_parallel(query, max_workers=8, progress_callback=update_progress)

      if results:
          # Clear progress display and show completion
          progress_bar.progress(1.0)
          status_text.success(f"✅ Search Complete! Found {len(results)} unique leads")
          
          # Save results to database
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
          progress_bar.progress(0)
          status_text.warning("⚠️ No new intelligence found.")

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
                # Create containers for progress display
                progress_bar = st.progress(0)
                status_text = st.empty()
                results_text = st.empty()
                
                def update_progress(completed, total, url, code):
                    """Callback function to update progress bar in real-time"""
                    # Clamp progress percent to [0.0, 1.0] to prevent Streamlit API errors
                    progress_percent = min(completed / total, 1.0)
                    status_icon = "✅" if code == 200 else "❌"
                    # Handle None URL gracefully
                    if url and url != "error":
                        url_display = url.split('/')[-1][:40]
                    else:
                        url_display = "error" if url == "error" else "unknown"
                    status_text.write(f"🔍 Pinging... **{url_display}** {status_icon} ({completed}/{total} checked)")
                    progress_bar.progress(progress_percent)
                
                # Run concurrent status check with progress callback
                results = check_link_status_concurrent(
                    updates, 
                    es_client, 
                    st.session_state["current_thread_id"],
                    max_workers=10,
                    progress_callback=update_progress
                )
                
                # Show summary
                alive = sum(1 for _, code in results if code == 200)
                dead = len(results) - alive
                
                progress_bar.progress(1.0)
                status_text.success(f"✅ Status check complete!")
                results_text.info(f"📊 Results: **{alive}** active 🟢 | **{dead}** down 🔴")
                
                time.sleep(1)
                st.rerun()
            
            # --- DELETE ALL DEAD LINKS BUTTON ---
            # Displays "Delete All Dead Links" button to remove all links with status code != 200
            if st.button("🗑️ Delete All Dead Links", key="delete_all_dead"):
                # Filter for dead links (status code not 200 or 0)
                dead_links = [u for u in updates if u.get('last_status_code') not in [200, 0]]
                
                if dead_links:
                    # Delete each dead link from the database
                    for link in dead_links:
                        try:
                            database.delete_intel_update(
                                es_client, 
                                st.session_state["current_thread_id"], 
                                link.get('onion_url')
                            )
                        except Exception as e:
                            print(f"Error deleting {link.get('onion_url')}: {e}")
                    
                    st.success(f"✅ Deleted {len(dead_links)} dead links")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.info("ℹ️ No dead links to delete. All links are either active or untested.")

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
                
                # --- BAN BUTTONS SECTION ---
                # Create three columns: one for Ban Locally, one for Ban Globally, one for Delete
                c1, c2, c3, c4 = st.columns([1, 1, 1, 3])
                
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
                                    tags=update.get('tags', []),
                                    last_status_code=200
                                )
                                    st.success("Extracted!")
                                    st.rerun()
                            else:
                                st.error("Site unreachable.")
                
                # --- BAN LOCALLY BUTTON ---
                # Removes link from this thread and prevents it from appearing in future scans
                with c2:
                    if st.button("🚫 Ban Local", key=f"ban_local_{update.get('onion_url')}"):
                        try:
                            database.ban_link_locally(
                                es_client, 
                                st.session_state["current_thread_id"], 
                                update.get('onion_url')
                            )
                            database.delete_intel_update(
                                es_client, 
                                st.session_state["current_thread_id"], 
                                update.get('onion_url')
                            )
                            st.success("✅ Locally banned & removed")
                            time.sleep(0.5)
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error banning link: {e}")
                
                # --- BAN GLOBALLY BUTTON ---
                # Removes link from all threads and prevents it from appearing in any future scans
                with c3:
                    if st.button("🛑 Ban Global", key=f"ban_global_{update.get('onion_url')}"):
                        try:
                            database.ban_link_globally(
                                es_client, 
                                update.get('onion_url')
                            )
                            # Delete from ALL threads
                            deleted_count = database.delete_link_from_all_threads(
                                es_client,
                                update.get('onion_url')
                            )
                            st.success(f"✅ Globally banned & removed from {deleted_count} thread(s)")
                            time.sleep(0.5)
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error banning link: {e}")
                
                with c4:
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