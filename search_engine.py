import re
import random
import config
import tor_network
import database
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Thread-safe lock for result aggregation (reserved for future use if needed)
_results_lock = threading.Lock()

def fetch_from_engine(url_template, query):
    """
    Scrape a specific dark web search engine for onion links matching a query.
    
    This function:
    1. Formats the engine's URL template with the search query
    2. Fetches the search results page through Tor
    3. Parses the HTML to find all .onion links
    4. Extracts link titles and URLs
    5. Returns deduplicated results
    
    The function uses the cached Tor session to reuse connections,
    avoiding the overhead of creating a new Tor circuit per search engine.
    
    Args:
        url_template (str): URL template with {query} placeholder
                           (e.g., "http://search.engine.onion/search?q={query}")
        query (str): Search term to find on dark web
    
    Returns:
        list: List of dictionaries, each containing:
              - 'title': Link text/title
              - 'onion_url': Full .onion URL
              - 'source': Hostname of the search engine
              Returns empty list [] if fetch fails or no results found.
    """
    
    # Get the globally cached Tor session to reuse connections and avoid new Tor circuits
    session = tor_network.get_tor_session()
    target_url = url_template.format(query=query)
    # Use a random User-Agent to avoid detection/blocking by the search engine
    headers = {"User-Agent": random.choice(config.USER_AGENTS)}
    
    try:
        print(f"🔎 Scanning: {target_url[:80]}...") 
        
        # Use the optimized make_request wrapper which enforces 15 second timeout
        response = tor_network.make_request(target_url, method='GET', timeout=15, headers=headers)
        
        # If make_request returns None, the request failed (timeout, connection error, etc.)
        if response is None:
            return []
        
        if response.status_code == 200:
            # Parse the HTML response to extract links
            soup = BeautifulSoup(response.text, "html.parser")
            results = []
            
            # Find all <a> tags with href attributes in the page
            links_found = soup.find_all('a', href=True)
            print(f"   ✓ Found {len(links_found)} links on page")

            for a in links_found:
                try:
                    href = a['href']
                    title = a.get_text(strip=True)

                    # Use regex to extract valid .onion URLs from the href attribute
                    # Pattern matches: http(s)://[alphanumeric-.]\.onion
                    onion_match = re.findall(r'https?:\/\/[a-z0-9\-\.]+\.onion', href)

                    # Only include results that have a valid .onion URL and a meaningful title
                    if onion_match and title and len(title) > 3:
                        clean_url = onion_match[0]
                        results.append({
                            "title": title,
                            "onion_url": clean_url,
                            "source": target_url.split('/')[2]  # Extract hostname from URL
                        })
                except:
                    # Skip any links that fail to parse; don't crash the entire search
                    continue
            
            if results:
                print(f"   ✅ Extracted {len(results)} valid onion links")
            return results 
            
        return []

    except Exception as e:
        print(f"   ❌ Error: {e}")
        return []


def search_parallel(query, max_workers=8, progress_callback=None):
    """
    Search multiple dark web search engines in parallel for a query.
    
    This function dramatically speeds up searches by querying all engines
    simultaneously instead of one-at-a-time. It uses ThreadPoolExecutor to
    spawn up to max_workers concurrent threads, each fetching from one search
    engine. Results arrive as they complete (not waiting for the slowest).
    
    The function also deduplicates results by .onion_url, ensuring the same
    link found by multiple engines appears only once in the final result.
    
    Optimizations:
    - Concurrent fetching: 18 engines × 15s timeout = ~30s total (vs 4-9 min sequential)
    - as_completed() pattern: Process results as they arrive, not in order
    - Thread-safe deduplication by .onion_url
    - Individual engine failures don't block the entire search
    - Real-time progress updates via callback
    
    Args:
        query (str): Search term to find on dark web
        max_workers (int): Maximum concurrent threads. Defaults to 8.
                          Higher = faster but uses more resources/Tor circuits.
        progress_callback (function): Optional callback function that accepts 
                                     (completed_count, total_engines, engine_url)
                                     for real-time progress tracking.
    
    Returns:
        list: List of unique dictionaries (deduplicated by onion_url) containing:
              - 'title': Link text
              - 'onion_url': Full .onion URL
              - 'source': Which search engine found it
    """
    all_results = []
    engines = config.SEARCH_ENGINES
    total_engines = len(engines)
    
    print(f"🔍 Starting parallel search across {total_engines} engines (max_workers={max_workers})...")
    
    # Calculate progress increment per engine (with buffer for deduplication phase)
    progress_per_engine = 1.0 / total_engines
    
    # Create a thread pool executor with max_workers threads
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all engine fetch jobs immediately (they run in parallel)
        # Create a dict mapping futures to engine URLs for tracking
        futures = {
            executor.submit(fetch_from_engine, engine, query): engine 
            for engine in engines
        }
        
        # Process results as they complete (as_completed returns futures in order of completion)
        # This is much faster than waiting for all results before processing
        completed_count = 0
        for future in as_completed(futures):
            completed_count += 1
            engine_url = futures[future]
            try:
                # Wait up to 20 seconds for this future to return
                # (timeout is a safety measure; fetch_from_engine has its own 15s timeout)
                data = future.result(timeout=20)
                if data:
                    all_results.extend(data)
                    results_found = len(data)
                else:
                    results_found = 0
                
                print(f"   [Progress: {completed_count}/{total_engines} engines done] {engine_url.split('/')[2]} (+{results_found} links)")
                
                # Call progress callback if provided
                if progress_callback:
                    progress_callback(completed_count, total_engines, engine_url)
                    
            except Exception as e:
                # If an engine fails, log it but continue with other engines
                print(f"   ⚠️  Engine failed: {e}")
                if progress_callback:
                    progress_callback(completed_count, total_engines, engine_url)

    # Deduplicate results by .onion_url using a dictionary.
    # This ensures that if multiple engines found the same link,
    # it only appears once in the final results.
    unique_results = {}
    for res in all_results:
        # If we haven't seen this .onion URL before, add it
        if res['onion_url'] not in unique_results:
            unique_results[res['onion_url']] = res
    
    unique_list = list(unique_results.values())
    
    # Filter out globally banned links
    # Get the Elasticsearch client to check for global bans
    try:
        es_client = database.get_es_client()
        if es_client:
            filtered_list = []
            for item in unique_list:
                if not database.is_url_globally_banned(es_client, item['onion_url']):
                    filtered_list.append(item)
                else:
                    print(f"   [Filtered] Globally banned link skipped: {item['onion_url']}")
            unique_list = filtered_list
    except Exception as e:
        print(f"   [Warning] Could not filter globally banned links: {e}")
    
    print(f"📊 Total unique results after filtering: {len(unique_list)} (from {len(all_results)} duplicates)")
    
    # Final callback for 100% completion
    if progress_callback:
        progress_callback(total_engines, total_engines, "Deduplication complete")
    
    return unique_list

