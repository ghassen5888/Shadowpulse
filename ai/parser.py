"""HTML parsing and text normalization for CTI extraction."""

from bs4 import BeautifulSoup


def clean_html_to_text(html_content: str) -> str:
    """Convert raw HTML into normalized plaintext for downstream extraction."""
    if not html_content:
        return ""

    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "iframe", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)
