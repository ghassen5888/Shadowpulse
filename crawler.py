import tor_network
from bs4 import BeautifulSoup
import time

def fetch_onion_content(url, timeout=15):
    """
    Fetch and parse content from an onion site, cleaning HTML and extracting text.
    
    This function:
    1. Fetches the HTML from a given onion URL through Tor
    2. Parses the HTML structure with BeautifulSoup
    3. Removes script and style tags that don't contain useful content
    4. Extracts plain text from the remaining HTML
    5. Normalizes whitespace (collapses multiple spaces/newlines)
    6. Truncates the output to prevent memory issues
    
    The function uses the cached Tor session to reuse connections, avoiding
    the overhead of creating a new Tor circuit.
    
    Args:
        url (str): Onion URL to fetch (must be a valid .onion address)
        timeout (int): Request timeout in seconds. Defaults to 15 seconds.
                      If the server doesn't respond within this time, returns None.
    
    Returns:
        str: Cleaned, plain text content from the page (up to 500KB),
             or None if the fetch fails, times out, or returns non-200 status code.
    """
    print(f"[Crawler] Visiting: {url}")
    
    try: 
        # Use the optimized make_request wrapper which enforces timeout and
        # uses the cached Tor session to reuse connections
        response = tor_network.make_request(url, method='GET', timeout=timeout)
        
        # If make_request returns None, the request failed (timeout, connection error, etc.)
        if response is None:
            print(f"[Crawler] Request failed or timed out")
            return None
        
        if response.status_code == 200:
            # Parse the HTML using BeautifulSoup to identify and extract content
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove <script> and <style> tags entirely from the DOM.
            # These don't contain useful content for text extraction, only code/styling.
            # decompose() removes them from the tree so they won't be text-extracted.
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Extract all remaining text from the HTML tags
            text = soup.get_text()
            
            # Normalize whitespace by splitting on any whitespace and rejoining with single space.
            # This collapses multiple spaces, tabs, and newlines into single spaces.
            clean_text = " ".join(text.split())
            
            # Truncate to prevent memory issues (500KB = 500,000 characters).
            # Some pages are extremely large and could consume all available memory.
            max_length = 500000
            if len(clean_text) > max_length:
                clean_text = clean_text[:max_length] + "\n... [Truncated]"
            
            print(f"[Crawler] ✅ Successfully extracted {len(clean_text)} characters")
            return clean_text
        else:
            # HTTP error (404, 500, 403, etc.)
            print(f"[Crawler] ❌ HTTP {response.status_code}")
            return None

    except Exception as e:
        # Catch any unexpected errors (malformed HTML, encoding issues, etc.)
        print(f"[Crawler] ❌ Error: {e}")
        return None


def fetch_onion_content_batch(urls, max_workers=5, timeout=15): # not yet in use
    """
    Fetch and parse content from multiple onion sites concurrently.
    
    This function is useful when you need to crawl a list of URLs simultaneously,
    rather than waiting for each one to complete sequentially. It uses ThreadPoolExecutor
    to spawn multiple threads that fetch URLs in parallel.
    
    Each URL is processed independently:
    - Fetched in parallel (up to max_workers concurrent threads)
    - Subject to the same timeout enforcement
    - Cleaned and parsed identically to fetch_onion_content()
    - Failed URLs are recorded with None as the value
    
    This function completes when all URLs have been attempted, not when the
    slowest URL finishes. Individual failures don't block other URLs.
    
    Args:
        urls (list): List of onion URLs to fetch (e.g., ['http://site1.onion', 'http://site2.onion'])
        max_workers (int): Maximum number of concurrent threads. Defaults to 5.
                          Higher values = faster but more resource usage/Tor circuits.
        timeout (int): Per-request timeout in seconds. Defaults to 15 seconds.
    
    Returns:
        dict: Dictionary mapping each URL to its content:
              - Key: Original URL
              - Value: Cleaned text content (str), or None if fetch failed
              Example: {'http://site1.onion': 'Site content...', 'http://site2.onion': None}
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    print(f"[Crawler] Batch fetching {len(urls)} URLs (max_workers={max_workers})")
    
    results = {}
    
    # Create a thread pool executor that manages up to max_workers threads
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all fetch jobs immediately to the thread pool.
        # Create a dict mapping futures to URLs so we can track which URL each result belongs to.
        futures = {
            executor.submit(fetch_onion_content, url, timeout): url 
            for url in urls
        }
        
        # Process results as they complete (as_completed returns futures in order of completion).
        # This approach doesn't wait for the slowest URL before processing others.
        completed = 0
        for future in as_completed(futures):
            completed += 1
            url = futures[future]
            try:
                # Wait up to timeout + 5 seconds for the future to return.
                # (fetch_onion_content already has its own timeout enforcement)
                content = future.result(timeout=timeout + 5)
                results[url] = content
                print(f"[Crawler] [Progress: {completed}/{len(urls)}]")
            except Exception as e:
                # If fetching this URL fails, record None for this URL and continue with others
                print(f"[Crawler] Failed to fetch {url}: {e}")
                results[url] = None
    
    # Print a summary of the batch operation
    successful_count = sum(1 for c in results.values() if c is not None)
    failed_count = sum(1 for c in results.values() if c is None)
    print(f"[Crawler] Batch complete: {successful_count} successful, {failed_count} failed")
    return results

