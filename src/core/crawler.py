import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup

from src.network import tor_network


def _extract_onion_urls(value):
    if not value:
        return []
    pattern = re.compile(r"https?:\/\/[a-z0-9\-\.]+\.onion(?:\/[^\s\"'>]*)?", re.IGNORECASE)
    return [match.rstrip(".,;:") for match in pattern.findall(value)]


def parse_onion_html(html_content, source_url=None):
    """Extract onion links from HTML content in a resilient way."""
    if not html_content:
        return []

    soup = BeautifulSoup(html_content, "html.parser")
    links = []
    seen = set()

    for tag in soup.find_all(["a", "link"], href=True):
        try:
            href = str(tag.get("href", "")).strip()
            if not href:
                continue
            onion_urls = _extract_onion_urls(href)
            if not onion_urls:
                continue
            onion_url = onion_urls[0]
            if onion_url in seen:
                continue
            seen.add(onion_url)
            title = " ".join(str(tag.get_text(" ", strip=True)).split())
            if not title:
                title = onion_url
            links.append({"title": title[:220], "onion_url": onion_url, "source": source_url or onion_url})
        except Exception:
            continue

    return links


def fetch_onion_content(url, timeout=15, telemetry_callback=None):
    """Fetch and parse content from an onion site while handling timeouts and malformed HTML."""
    print(f"[Crawler] Visiting: {url}")
    try:
        response = tor_network.make_request(
            url,
            method="GET",
            timeout=timeout,
            telemetry_callback=telemetry_callback,
            engine_name=url,
        )
        if response is None:
            print("[Crawler] Request failed or timed out")
            return None

        if response.status_code != 200:
            print(f"[Crawler] ❌ HTTP {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        text = soup.get_text(" ", strip=True)
        clean_text = " ".join(text.split())
        max_length = 500000
        if len(clean_text) > max_length:
            clean_text = clean_text[:max_length] + "\n... [Truncated]"

        print(f"[Crawler] ✅ Successfully extracted {len(clean_text)} characters")
        return clean_text
    except Exception as exc:
        print(f"[Crawler] ❌ Error: {exc}")
        return None


def fetch_onion_content_batch(urls, max_workers=5, timeout=15):
    """Fetch multiple onion pages concurrently and aggregate the results."""
    print(f"[Crawler] Batch fetching {len(urls)} URLs (max_workers={max_workers})")
    results = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_onion_content, url, timeout): url for url in urls}
        completed = 0
        for future in as_completed(futures):
            completed += 1
            url = futures[future]
            try:
                content = future.result(timeout=timeout + 5)
                results[url] = content
                print(f"[Crawler] [Progress: {completed}/{len(urls)}]")
            except Exception as exc:
                print(f"[Crawler] Failed to fetch {url}: {exc}")
                results[url] = None

    successful_count = sum(1 for content in results.values() if content is not None)
    failed_count = sum(1 for content in results.values() if content is None)
    print(f"[Crawler] Batch complete: {successful_count} successful, {failed_count} failed")
    return results
