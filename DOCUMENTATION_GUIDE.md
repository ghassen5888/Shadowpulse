# Shadowpulse Code Documentation Guide

## Overview
All code files in Shadowpulse have been enhanced with comprehensive docstrings and inline comments to improve readability and aid in studying/presenting the codebase.

---

## File Documentation Summary

### 1. **tor_network.py** - Tor Proxy & Connection Management
**Key Functions:**
- `setup_tor()`: Verifies Tor daemon is running
- `get_tor_session()`: Creates cached Tor session with connection pooling (decorated with `@st.cache_resource`)
- `make_request()`: Wrapper for HTTP requests with timeout enforcement

**Documentation Highlights:**
- Explains why connection pooling is essential (80-90% faster requests)
- Describes SOCKS5h proxy configuration and why DNS queries must be routed through Tor
- Details exponential backoff retry strategy (0.5s, 1s, 2s delays)
- Documents timeout enforcement to prevent hanging requests

---

### 2. **search_engine.py** - Dark Web Search
**Key Functions:**
- `fetch_from_engine()`: Scrapes a single search engine for .onion links
- `search_parallel()`: Parallel search across 18 search engines using ThreadPoolExecutor

**Documentation Highlights:**
- Explains regex pattern matching for .onion URLs
- Describes how as_completed() processes results as they arrive (5-10x faster than sequential)
- Documents thread-safe deduplication by .onion_url
- Shows how individual engine failures don't block the entire search

---

### 3. **crawler.py** - Content Crawling
**Key Functions:**
- `fetch_onion_content()`: Fetch and parse content from a single onion site
- `fetch_onion_content_batch()`: Concurrent crawling of multiple URLs

**Documentation Highlights:**
- Explains HTML cleaning (removing script/style tags, normalizing whitespace)
- Documents memory-safe truncation to 500KB limit
- Describes why HEAD requests are preferred for status checking
- Shows batch processing with concurrent fetching

---

### 4. **dashboard.py** - Streamlit UI & User Interactions
**Key Functions:**
- `check_link_status_concurrent()`: Multithreaded link status checking (inner function: `ping_single_url()`)

**Documentation Highlights:**
- Explains why this prevents UI freezing (10x faster than sequential)
- Documents inner `ping_single_url()` function for clarity
- Shows thread-safe database updates during concurrent operations
- Describes how ThreadPoolExecutor context is separate from Streamlit's main loop

---

### 5. **database.py** - Elasticsearch Integration
**Key Functions:**
- `get_es_client()`: Connect to Elasticsearch with timeout enforcement
- `create_thread()`: Create a new operation/case
- `get_all_threads()`: Retrieve all operations
- `save_intel_update()`: Save discovered links
- `get_thread_data()`: Retrieve intel for a specific thread
- `update_link_status()`: Update HTTP status codes
- `get_dashboard_stats()`: Aggregate statistics for dashboard

**Documentation Highlights:**
- Explains document structure (type-based classification: "thread" vs "intel_update")
- Documents unique ID strategy to prevent duplicates
- Describes Elasticsearch query syntax (bool queries, term filters, aggregations)
- Shows how aggregation queries efficiently compute per-operation statistics

---

## Documentation Structure

Each file follows this pattern:

### 1. **Module-Level Docstring**
```python
"""
Brief description of what this module does.

Additional details about purpose and key concepts.
"""
```

### 2. **Function Docstrings** (Google Style)
```python
def function_name(arg1, arg2):
    """
    One-line summary of what the function does.
    
    Detailed explanation of:
    - What it does (step-by-step if complex)
    - Why it's implemented this way
    - Key optimizations or design decisions
    
    Args:
        arg1 (type): Description
        arg2 (type): Description
    
    Returns:
        type: Description of return value
    """
```

### 3. **Inline Comments**
Comments appear **above** complex lines explaining:
- **Why** we're doing something (not just what)
- Design decisions and trade-offs
- Performance implications
- Thread safety considerations
- Timeout and error handling logic

---

## Key Concepts Documented

### Performance & Optimization
- **Connection Pooling**: Why reusing TCP connections saves 80-90% overhead
- **ThreadPoolExecutor**: How parallel processing works with `as_completed()`
- **Caching**: Why `@st.cache_resource` is used for Tor session
- **Timeout Strategy**: Strict enforcement at multiple levels (per-request and per-future)

### Concurrency & Threading
- Thread-safe operations (locks, atomic operations)
- How ThreadPoolExecutor doesn't freeze Streamlit UI
- Graceful error handling per thread (individual failures don't block all)

### Dark Web & Tor
- SOCKS5h proxy routing (DNS through Tor is important)
- Connection reuse vs new circuits (5-15s overhead per new circuit)
- Random User-Agent selection to avoid blocking

### Elasticsearch
- Document types and indexing strategy
- Query syntax (bool queries, term filters, aggregations)
- Unique ID design to prevent duplicates
- Partial updates vs full document replacement

---

## For Presentations

Use the inline comments to explain:

1. **Architecture**: How the modules work together
   - Tor session reuse (tor_network.py)
   - Parallel searches (search_engine.py)
   - Concurrent crawling (crawler.py)
   - Thread-safe DB updates (database.py)

2. **Performance**: Why this is 10x faster
   - Before: Sequential requests to 18 engines (4-9 min)
   - After: Parallel requests (30-60 sec)
   - Before: 100 links checked sequentially with frozen UI (25+ min)
   - After: 100 links checked in parallel (2-3 min) + responsive UI

3. **Code Quality**: Design patterns used
   - Connection pooling (HTTPAdapter)
   - Thread pool executor (concurrent.futures)
   - Caching (Streamlit's st.cache_resource)
   - Error handling (graceful degradation)

---

## Quick Reference

| File | Functions | Key Pattern | Performance Gain |
|------|-----------|------------|-----------------|
| `tor_network.py` | 3 | Connection pooling + caching | 80-90% faster requests |
| `search_engine.py` | 2 | ThreadPoolExecutor + as_completed | 5-10x faster search |
| `crawler.py` | 2 | Batch fetching with concurrent.futures | 3-5x faster per URL |
| `dashboard.py` | 1 | ThreadPoolExecutor for UI non-blocking | 10x faster + responsive UI |
| `database.py` | 7 | Elasticsearch aggregation queries | Sub-second response |

---

## How to Use This Documentation

**For Study:**
1. Read function docstrings first (understand the "what")
2. Read inline comments (understand the "why")
3. Study the code logic (understand the "how")

**For Presentation:**
1. Start with module overview (docstring at top)
2. Highlight key functions and their docstrings
3. Zoom in on inline comments explaining complex parts
4. Show performance comparisons (before/after)

**For Development:**
1. Use docstrings as API reference
2. Follow the same pattern for new functions
3. Add inline comments for non-obvious decisions
4. Keep comments focused on "why", not "what the code does"

**steps**
1. cd elasticsearch & ./bin/elsticsearch : host the db
2. sudo service tor start 
3. source /venv/bin/activate
4. streamlit run dashboard.py
