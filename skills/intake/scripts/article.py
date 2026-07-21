"""
Article Extractor — fetches a URL, extracts clean text via readability.

Exports:
    process(url: str, domain: str = DEFAULT_DOMAIN) -> dict
"""

from _config import DEFAULT_DOMAIN, STORE_BASE
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from readability import Document

# ── helpers ──────────────────────────────────────────────────────────────

def _extract_meta(soup: BeautifulSoup, name: str) -> str | None:
    """Extract a meta tag value by name or property attribute."""
    for attr in ("name", "property"):
        tag = soup.find("meta", attrs={attr: name})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def _parse_date(raw: str | None) -> str | None:
    """Try to parse a date string into YYYY-MM-DD; return None on failure."""
    if not raw:
        return None
    # ISO-8601 / common date formats
    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%a, %d %b %Y %H:%M:%S %z",
        "%B %d, %Y",
        "%d %B %Y",
    ):
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _extract_domain(url: str) -> str:
    """Return the registered domain from a URL."""
    parsed = urlparse(url)
    host = parsed.netloc or parsed.hostname or ""
    # Strip leading www.
    return re.sub(r"^www\.", "", host).lower()


def _is_html_content(headers: dict) -> bool:
    """Check Content-Type header to see if response is HTML."""
    ct = headers.get("Content-Type", "").lower()
    return any(
        hint in ct for hint in ("text/html", "application/xhtml", "text/plain")
    )


# ── public API ───────────────────────────────────────────────────────────

def process(url: str, domain: str = DEFAULT_DOMAIN) -> dict:
    """
    Fetch *url*, extract clean text and metadata, return a structured dict.

    Parameters
    ----------
    url : str
        URL to extract article content from.
    domain : str, optional
        Domain slug (default from INTAKE_DOMAIN). Included in the result as domain.

    Returns
    -------
    dict with keys: status, type, data (or error).
    """
    try:
        resp = requests.get(
            url,
            timeout=30,
            headers={"User-Agent": "SAC-Intake/1.0"},
        )
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        return {
            "status": "error",
            "type": "article",
            "error": f"Request timed out after 30s: {url}",
        }
    except requests.exceptions.RequestException as exc:
        return {
            "status": "error",
            "type": "article",
            "error": f"Request failed: {exc}",
        }

    # ── reject non-HTML content ──────────────────────────────────────────
    if not _is_html_content(resp.headers):
        ct = resp.headers.get("Content-Type", "unknown")
        if "pdf" in ct.lower():
            return {
                "status": "error",
                "type": "article",
                "error": f"Cannot extract article from PDF: {url}",
            }
        return {
            "status": "error",
            "type": "article",
            "error": f"Unexpected Content-Type '{ct}' for URL: {url}",
        }

    # ── parse ────────────────────────────────────────────────────────────
    html = resp.text
    soup = BeautifulSoup(html, "lxml")

    # readability extraction (works gracefully on paywalled pages)
    doc = Document(html)
    clean_html = doc.summary()
    clean_soup = BeautifulSoup(clean_html, "lxml")
    text = clean_soup.get_text(separator="\n", strip=True)

    # ── metadata ─────────────────────────────────────────────────────────
    title = doc.title() or _extract_meta(soup, "og:title")
    author = _extract_meta(soup, "author") or _extract_meta(
        soup, "article:author"
    )
    date_raw = (
        _extract_meta(soup, "article:published_time")
        or _extract_meta(soup, "date")
        or _extract_meta(soup, "dc.date")
    )
    date = _parse_date(date_raw)

    return {
        "status": "ok",
        "type": "article",
        "data": {
            "title": title or "Untitled",
            "author": author or None,
            "date": date,
            "url": resp.url,  # final URL after redirects
            "text": text,
            "text_length": len(text),
            "domain": _extract_domain(resp.url),
            "domain": domain,
        },
    }