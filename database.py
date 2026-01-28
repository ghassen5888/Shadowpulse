# database.py
"""
Database module for Shadowpulse.

This module provides an interface to Elasticsearch for storing and querying
intelligence data. It manages operations, links, and status tracking.
"""

from elasticsearch import Elasticsearch
import config
from datetime import datetime
import uuid
import os
import time
def get_es_client(max_retries=5, sleep_seconds=2):
    """
    Connect to the Elasticsearch database with retry logic.
    
    This function establishes a connection to the Elasticsearch server
    configured via the ES_HOST environment variable, with a fallback to
    localhost. It implements retry logic to handle startup race conditions
    where the app connects before Elasticsearch is fully ready.
    
    The connection is verified using client.ping() to ensure the server
    is actually responding before returning the client.
    
    Args:
        max_retries (int): Maximum number of connection attempts (default: 5)
        sleep_seconds (int): Seconds to wait between retry attempts (default: 2)
    
    Returns:
        Elasticsearch: An Elasticsearch client instance if connection succeeds,
                      or None if all connection attempts fail.
                      
    Raises:
        Prints error messages but doesn't raise exceptions.
    """
    # Get URL from environment variable (Docker) or fallback to localhost
    es_host = os.getenv("ES_HOST", "http://localhost:9200")
    print(f"🔌 DEBUG: Attempting to connect to Elasticsearch at: {es_host}")
    
    for attempt in range(max_retries):
        try:
            # Create Elasticsearch client
            client = Elasticsearch(
                es_host,
                request_timeout=30
            )
            
            # Actually ping to verify the connection works
            if client.ping():
                print("✅ DEBUG: Successfully connected to Elasticsearch!")
                
                # --- START FIX: Initialize Database with Schema ---
                if not client.indices.exists(index=config.INDEX_NAME):
                    print(f"🆕 Index '{config.INDEX_NAME}' not found. Creating with schema...")
                    
                    # Define the columns so sorting works immediately
                    mapping = {
                        "mappings": {
                            "properties": {
                                "url": {"type": "keyword"},
                                "title": {"type": "text"},
                                "content": {"type": "text"},
                                "scraped_at": {"type": "date"},  # <--- THIS FIXES THE ERROR
                                "thread_id": {"type": "keyword"}
                            }
                        }
                    }
                    client.indices.create(index=config.INDEX_NAME, body=mapping)
                    print("✅ Index created successfully with correct mapping.")
                # --- END FIX ---
                
                return client
            else:
                print(f"⚠️ DEBUG: Ping failed (Attempt {attempt + 1}/{max_retries})")
        
        except Exception as e:
            print(f"❌ DEBUG: Error connecting (Attempt {attempt + 1}/{max_retries}): {e}")
        
        # Wait before retrying (except on last attempt)
        if attempt < max_retries - 1:
            time.sleep(sleep_seconds)
    
    print("❌ CRITICAL: Could not connect to Elasticsearch after multiple attempts.")
    return None
def create_thread(client, thread_name):
    """
    Create a new operation/case thread in Elasticsearch.
    
    A "thread" is an operational case or investigation, identified by a unique ID.
    This function creates a new thread document in Elasticsearch with metadata
    about when it was created and its current status.
    
    Args:
        client (Elasticsearch): Elasticsearch client instance
        thread_name (str): Human-readable name for this operation (e.g., "Ransomware Group X")
    
    Returns:
        tuple: (thread_id, thread_name)
               - thread_id is a randomly generated 8-character ID
               - thread_name is the name passed in (for convenience)
    """
    # Generate a unique 8-character ID by taking the first 8 chars of a UUID
    thread_id = str(uuid.uuid4())[:8]
    
    # Create the document structure for this thread
    doc = {
      "type": "thread",              # Document type identifier
      "thread_id": thread_id,        # Unique thread/operation ID
      "name": thread_name,           # Human-readable operation name
      "created_at": datetime.now().isoformat(),  # ISO format timestamp of creation
      "status": "active"             # All new threads start as "active"
    }
    
    # Insert the document into Elasticsearch.
    # The ID is prefixed with "thread_" to avoid conflicts with other document types.
    client.index(index=config.INDEX_NAME, id=f"thread_{thread_id}", document=doc)
    return thread_id, thread_name

def get_all_threads(client):
    """
    Retrieve all operation/case threads from Elasticsearch.
    
    This function queries Elasticsearch for all documents with type="thread",
    returning their IDs and names. Used to populate the sidebar selectbox.
    
    Args:
        client (Elasticsearch): Elasticsearch client instance
    
    Returns:
        list: List of dictionaries: [{"id": "abc123", "name": "Operation X"}, ...]
              Returns empty list if no threads exist.
    """
    # Query Elasticsearch for documents where type.keyword field equals "thread"
    # (keyword type for exact matching; no partial matches)
    query = {"term": {"type.keyword": "thread"}}
    
    # Execute the search with a size limit of 100 threads
    resp = client.search(index=config.INDEX_NAME, query=query, size=100)
    
    # Extract thread ID and name from each search result hit
    return [{"id": h['_source']['thread_id'], "name": h['_source']['name']} for h in resp['hits']['hits']]

def save_intel_update(client, thread_id, url, title, content, tags=[]):
    """
    Save an intelligence update (discovered link) to Elasticsearch.
    
    An "intel_update" is a discovered onion URL with associated metadata
    (title, content, tags, status). This function creates a new intel document
    linked to a specific thread.
    
    Args:
        client (Elasticsearch): Elasticsearch client instance
        thread_id (str): The operation/thread this intel belongs to
        url (str): The onion URL that was discovered
        title (str): Link title or heading text
        content (str): Full page content or summary
        tags (list): Optional list of tags/keywords (defaults to empty list)
    
    Returns:
        None. Prints status to console.
    """
    # Create the intel update document structure
    doc = {
        "type": "intel_update",                    # Document type identifier
        "thread_id": thread_id,                    # Link this intel to a thread
        "onion_url": url,                          # The discovered .onion URL
        "title": title,                            # Page title or link text
        "summary": content[:500] + "...",          # First 500 characters as summary
        "full_content": content,                   # Full page content for deep search
        "scraped_at": datetime.now().isoformat(), # ISO timestamp of when we scraped it
        "tags": tags,                              # User-defined tags for search/filter
        "last_status_code": 0                      # 0 = unknown/not yet checked
    }
    
    # Create a unique ID by combining thread_id and URL.
    # This prevents duplicates: if the same URL is added to a thread twice,
    # the second save will overwrite the first (not create a duplicate).
    unique_id = f"{thread_id}_{url}"
    client.index(index=config.INDEX_NAME, id=unique_id, document=doc)
    print(f"[Database] Attached intel to Thread {thread_id}")

def get_thread_data(client, thread_id):
    """
    Retrieve all intel updates (discovered links) for a specific thread.
    """
    # FIX: "thread_id" is already a keyword field, so we don't use .keyword
    # "type" is likely auto-mapped as text, so .keyword is safe there.
    query = {
        "bool": {
            "must": [
                {"term": {"type.keyword": "intel_update"}},  # This is fine
                {"term": {"thread_id": thread_id}}           # <--- CHANGED: Removed .keyword
            ]
        }
    }
    
    # Execute the search
    resp = client.search(index=config.INDEX_NAME, query=query, size=100, sort=[{"scraped_at": "desc"}])
    
    return [h['_source'] for h in resp['hits']['hits']]

def update_link_status(client, thread_id, url, status_code):
    """
    Update the HTTP status code for a discovered link.
    
    This function is called after pinging a link to record whether it's
    online (200), down (500), not found (404), etc. The status code is
    used to display link health in the dashboard (green check vs red X).
    
    Args:
        client (Elasticsearch): Elasticsearch client instance
        thread_id (str): The operation/thread containing this link
        url (str): The onion URL to update
        status_code (int): HTTP status code (200=OK, 404=Not Found, 500=Error, etc.)
    
    Returns:
        bool: True if update succeeded, False if it failed.
    """
    # Construct the unique document ID (matches the ID used in save_intel_update)
    unique_id = f"{thread_id}_{url}"
    
    try: 
        # Update only the last_status_code field (partial update, not full replacement)
        client.update(index=config.INDEX_NAME, id=unique_id, doc={"last_status_code": status_code}) 
        return True 
    except Exception as e: 
        print(f"Error updating status: {e}") 
        return False

def get_dashboard_stats(client):
    """
    Get statistics about all operations for the dashboard summary.
    
    This function computes per-operation statistics: how many links in each
    operation are currently online (status code 200). The results are displayed
    as a bar chart on the dashboard's welcome screen.
    
    The function:
    1. Retrieves all thread names (for mapping IDs to display names)
    2. Queries Elasticsearch for all intel updates with status 200 (online)
    3. Groups (aggregates) results by thread_id
    4. Counts how many online links are in each thread
    5. Returns a sorted list of {name, count} objects
    
    Args:
        client (Elasticsearch): Elasticsearch client instance
    
    Returns:
        list: List of dictionaries: [{"name": "Operation X", "count": 42}, ...]
              Count is the number of currently-online (.status_code == 200) links.
    """
    # Step 1: Get all thread names for mapping thread_id -> thread_name
    threads = get_all_threads(client)
    thread_map = {t['id']: t['name'] for t in threads}
    
    # Step 2: Build a query for all intel updates with status 200 (links currently online)
    query = {
        "bool": {
            "must": [
                {"term": {"type.keyword": "intel_update"}},  # Only intel documents, not threads
                {"term": {"last_status_code": 200}}          # Only links with HTTP 200 (online)
            ]
        }
    }
    
    # Step 3: Define an aggregation that groups results by thread_id.
    # "terms" aggregation groups documents by a field, "size": 10 limits to top 10 threads.
    aggs = {
        "by_thread": {
            "terms": { "field": "thread_id.keyword", "size": 10 }
        }
    }
    
    # Step 4: Execute the aggregation query.
    # size=0 means don't return individual documents, only aggregation results (more efficient).
    resp = client.search(index=config.INDEX_NAME, query=query, aggs=aggs, size=0)
    
    # Step 5: Build the stats list by iterating through aggregation buckets
    stats = []
    for bucket in resp['aggregations']['by_thread']['buckets']:
        t_id = bucket['key']                           # The thread_id value for this bucket
        count = bucket['doc_count']                    # Number of documents in this bucket (online links)
        t_name = thread_map.get(t_id, "Unknown Op")   # Get the thread name, or use "Unknown Op" if not found
        stats.append({"name": t_name, "count": count})
    
    return stats