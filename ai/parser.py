"""HTML parsing and text normalization for CTI extraction."""

import logging
from time import perf_counter

from bs4 import BeautifulSoup

LOGGER = logging.getLogger(__name__)


def clean_html_to_text(html_content: str) -> str:
    """Convert raw HTML into normalized plaintext for downstream extraction."""
    parse_start = perf_counter()
    raw_html_length = len(html_content or "")
    LOGGER.debug(
        "[SHADOWPULSE DEBUG] [PARSER] Starting HTML cleanup raw_html_chars=%d",
        raw_html_length,
    )
    if not html_content:
        LOGGER.debug("[SHADOWPULSE DEBUG] [PARSER] Empty HTML payload received")
        return ""

    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "iframe", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    clean_text = "\n".join(lines)
    clean_text_length = len(clean_text)
    parse_duration_ms = (perf_counter() - parse_start) * 1000.0
    LOGGER.debug(
        "[SHADOWPULSE DEBUG] [PARSER] Completed HTML cleanup raw_html_chars=%d clean_text_chars=%d duration_ms=%.1f",
        raw_html_length,
        clean_text_length,
        parse_duration_ms,
    )
    return clean_text
