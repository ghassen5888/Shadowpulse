import logging
import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from src.config import settings as config
from src.database import database
from src.network import tor_network

LOGGER = logging.getLogger(__name__)


def _display_name(url_template: str) -> str:
    try:
        parsed = urlparse(url_template)
        if parsed.netloc:
            return parsed.netloc
        return url_template.split("/")[2] if "/" in url_template else url_template
    except Exception:
        return url_template


def parse_onion_html(html_content, source_url=None):
    """Extract onion links from search result HTML without crashing on malformed markup."""
    if not html_content:
        return []

    soup = BeautifulSoup(html_content, "html.parser")
    results = []
    seen_urls = set()

    for tag in soup.find_all(["a", "link"], href=True):
        try:
            href = str(tag.get("href", "")).strip()
            if not href:
                continue

            onion_matches = re.findall(r"https?:\/\/[a-z0-9\-\.]+\.onion(?:\/[^\s\"'>]*)?", href, flags=re.IGNORECASE)
            if not onion_matches:
                continue

            onion_url = onion_matches[0].rstrip(".,;:)")
            if onion_url in seen_urls:
                continue
            seen_urls.add(onion_url)

            title = " ".join(str(tag.get_text(" ", strip=True)).split())
            if not title:
                title = " ".join(str(tag.get("title") or tag.get("aria-label") or "").split())
            if not title:
                title = onion_url

            results.append(
                {
                    "title": title[:220],
                    "onion_url": onion_url,
                    "source": source_url or _display_name(href),
                }
            )
        except Exception:
            continue

    return results


def fetch_from_engine(url_template, query, telemetry_callback=None):
    """Fetch a single search-engine page and return extracted onion links."""
    target_url = url_template.format(query=query)
    engine_name = _display_name(target_url)
    headers = {"User-Agent": random.choice(config.USER_AGENTS)}

    print(f"🔎 Scanning: {target_url[:90]}...")
    try:
        response = tor_network.make_request(
            target_url,
            method="GET",
            timeout=15,
            headers=headers,
            telemetry_callback=telemetry_callback,
            engine_name=engine_name,
        )
        if response is None:
            LOGGER.warning("Search engine %s returned no response", engine_name)
            return []

        if response.status_code != 200:
            LOGGER.warning("Search engine %s returned HTTP %s", engine_name, response.status_code)
            return []

        results = parse_onion_html(response.text, source_url=target_url)
        if results:
            print(f"   ✅ Extracted {len(results)} valid onion links from {engine_name}")
        else:
            print(f"   ℹ️ No parseable onion links from {engine_name}")
        return results
    except Exception as exc:
        LOGGER.exception("Search engine %s failed", engine_name)
        print(f"   ❌ Error: {exc}")
        return []


def search_parallel(query, max_workers=8, progress_callback=None, telemetry_callback=None):
    """Search multiple dark-web engines in parallel and deduplicate the results."""
    engines = list(config.SEARCH_ENGINES or [])
    total_engines = max(1, len(engines))
    max_workers = max(1, min(max_workers or 4, total_engines))

    print(f"🔍 Starting parallel search across {total_engines} engines (max_workers={max_workers})...")
    all_results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_from_engine, engine, query, telemetry_callback): engine
            for engine in engines
        }

        completed_count = 0
        for future in as_completed(futures):
            completed_count += 1
            engine_url = futures[future]
            engine_name = _display_name(engine_url)
            try:
                data = future.result(timeout=20)
                if data:
                    all_results.extend(data)
                    results_found = len(data)
                    status = "Completed"
                    detail = f"{results_found} links"
                else:
                    results_found = 0
                    status = "Completed"
                    detail = "No parseable onion links"

                print(f"   [Progress: {completed_count}/{total_engines}] {engine_name} (+{results_found} links)")
                if progress_callback:
                    progress_callback(completed_count, total_engines, engine_name, status, detail, 0, 0.0)
            except Exception as exc:
                LOGGER.exception("Engine %s failed", engine_name)
                if progress_callback:
                    progress_callback(completed_count, total_engines, engine_name, "Offline/Skipped", str(exc), 0, 0.0)

    unique_results = {}
    for res in all_results:
        onion_url = str(res.get("onion_url") or "").strip().lower()
        if not onion_url:
            continue
        if onion_url not in unique_results:
            unique_results[onion_url] = {
                **res,
                "onion_url": res.get("onion_url", ""),
            }

    unique_list = list(unique_results.values())

    try:
        es_client = database.get_es_client()
        if es_client:
            filtered_list = []
            for item in unique_list:
                onion_url = str(item.get("onion_url") or "").strip()
                if not database.is_url_globally_banned(es_client, onion_url):
                    filtered_list.append(item)
                else:
                    print(f"   [Filtered] Globally banned link skipped: {onion_url}")
            unique_list = filtered_list
    except Exception as exc:
        LOGGER.warning("Could not filter globally banned links: %s", exc)

    print(f"📊 Total unique results after filtering: {len(unique_list)} (from {len(all_results)} duplicates)")
    if progress_callback:
        progress_callback(total_engines, total_engines, "Deduplication", "Completed", "Resolved duplicates", 0, 0.0)

    return unique_list
