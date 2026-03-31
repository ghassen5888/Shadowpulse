# tor_network.py
import requests
from src.config import settings as config
import socks
import socket
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import streamlit as st

_GLOBAL_TOR_SESSION = None

def setup_tor():
    """
    Verify that the Tor daemon is running and accessible on the configured port.
    
    This function attempts to establish a socket connection to the Tor proxy
    to confirm it's running before any network requests are made.
    
    Returns:
        bool: True if Tor port is open and accessible, False otherwise.
    """
    try:
        # Create a test socket to check if Tor is listening on the configured port
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = test_socket.connect_ex((config.TOR_PROXY_IP, config.TOR_PORT))
        test_socket.close()

        if result == 0:
            print("✅ Tor Port (9050) is Open")
            return True
        else:
            print("❌ Tor Port (9050) is Closed. Is Tor running?")
            return False
            
    except Exception as e: 
        print(f"[Network] Tor check error: {e}")
        return False

@st.cache_resource
def get_tor_session():
    """
    Create and cache a single Tor session with connection pooling.
    
    This function creates a requests.Session object that is cached by Streamlit,
    meaning it's created only once per Streamlit session and reused for all
    subsequent requests. This dramatically improves performance by:
    - Reusing the same Tor circuit instead of creating a new one per request
    - Maintaining a pool of persistent connections (100 max)
    - Retrying failed requests with exponential backoff
    
    The session is configured with:
    - SOCKS5 proxy pointing to local Tor daemon (localhost:9050)
    - HTTPAdapter with connection pooling and retry strategy
    - Default User-Agent to avoid blocking
    
    Returns:
        requests.Session: A cached session object routed through Tor with pooling enabled.
    """
    session = requests.Session()
    
    # Configure SOCKS5 proxy to route all traffic through the Tor daemon.
    # socks5h means DNS queries are also routed through Tor (the 'h' is important)
    session.proxies = {
        'http':  'socks5h://localhost:9050',
        'https': 'socks5h://localhost:9050'
    }
    
    # Set a default User-Agent header to identify as a browser.
    # This helps avoid being blocked by websites that reject non-browser traffic.
    session.headers.update({ 
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    })

    # Create an HTTPAdapter with connection pooling and retry logic.
    # This adapter is crucial for reusing connections instead of creating a new Tor
    # circuit for every request, which would be extremely slow.
    adapter = HTTPAdapter(
        pool_connections=100,    # Number of connection pools to cache
        pool_maxsize=100,        # Maximum number of connections per pool
        pool_block=False,        # Don't block if pool is exhausted; create new connections
        max_retries=Retry(
            total=3,
            backoff_factor=0.5,  # Wait 0.5s, 1s, 2s between retries (exponential backoff)
            status_forcelist=[429, 500, 502, 503, 504],  # Retry on these HTTP errors
            allowed_methods=['GET', 'HEAD', 'PUT', 'DELETE']  # Only retry idempotent methods
        )
    )
    
    # Mount the adapter for both HTTP and HTTPS protocols.
    # This ensures all requests use the connection pooling strategy.
    session.mount("http://", adapter)
    session.mount("https://", adapter) 
    
    print("[Tor Network] Cached session created with connection pooling enabled.")
    return session

def make_request(url, method='GET', timeout=15, **kwargs):
    """
    Wrapper function to make HTTP requests through Tor with strict timeout enforcement.
    
    This function provides a unified interface for making requests through the cached
    Tor session. It handles different HTTP methods and enforces timeout limits to ensure
    requests fail fast if a site is slow or unresponsive.
    
    Args:
        url (str): Target URL to request
        method (str): HTTP method to use (GET, HEAD, POST, etc.). Defaults to 'GET'.
        timeout (int): Request timeout in seconds. Defaults to 15 seconds.
        **kwargs: Additional arguments passed directly to the underlying requests method
                 (e.g., headers, data, json, verify, etc.)
    
    Returns:
        requests.Response: The HTTP response object if successful, None if request fails.
                          Caller should check if return value is None before using it.
    """
    session = get_tor_session()
    
    try:
        # Route the request through the appropriate HTTP method, all routed through Tor proxy.
        # Using the cached session ensures connection pooling and reuse.
        if method.upper() == 'HEAD':
            return session.head(url, timeout=timeout, **kwargs)
        elif method.upper() == 'GET':
            return session.get(url, timeout=timeout, **kwargs)
        elif method.upper() == 'POST':
            return session.post(url, timeout=timeout, **kwargs)
        else:
            # For any other HTTP method (PUT, DELETE, PATCH, etc.)
            return session.request(method, url, timeout=timeout, **kwargs)
    except requests.exceptions.Timeout:
        # Timeout occurred - the server didn't respond within the specified timeout period
        print(f"[Tor Network] ⏱️  Timeout ({timeout}s) on {url}")
        return None
    except requests.exceptions.ConnectionError as e:
        # Connection failed - network issue or server unreachable
        print(f"[Tor Network] Connection error on {url}: {e}")
        return None
    except Exception as e:
        # Any other error (SSL, protocol, etc.)
        print(f"[Tor Network] Error on {url}: {e}")
        return None
