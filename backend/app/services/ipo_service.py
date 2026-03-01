"""
IPO tracking service using web scraping.
"""

import re
from typing import Any

import requests
from bs4 import BeautifulSoup

IPO_LIST_URL = "https://www.chittorgarh.com/ipo/ipo_list.asp"
MAX_IPOS = 5
REQUEST_TIMEOUT = 15
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _extract_ipo_from_detail_page(url: str, name: str) -> dict[str, str] | None:
    """Parse a single IPO detail page and extract data."""
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text()

    # Open date: "IPO Open" followed by "Wed, Mar 4, 2026"
    open_match = re.search(r"IPO Open\s*([A-Za-z]+, [A-Za-z]+ \d+, \d{4})", text)
    open_date = open_match.group(1).strip() if open_match else "N/A"

    # Close date
    close_match = re.search(r"IPO Close\s*([A-Za-z]+, [A-Za-z]+ \d+, \d{4})", text)
    close_date = close_match.group(1).strip() if close_match else "N/A"

    # Price band: "₹1287 to ₹1352" or "1287 to 1352"
    price_match = re.search(
        r"Price Band[^\d]*(?:[\u20b9₹]?\s*)?(\d[\d,]*)\s*to\s*(?:[\u20b9₹]?\s*)?(\d[\d,]*)",
        text,
        re.IGNORECASE,
    )
    if not price_match:
        price_match = re.search(r"(\d{3,5})\s*to\s*(\d{3,5})", text)
    price_band = (
        f"{price_match.group(1)} to {price_match.group(2)}"
        if price_match
        else "N/A"
    )

    # GMP - often not on chittorgarh, link goes to investorgain
    gmp_match = re.search(
        r"GMP[:\s]+(?:₹|Rs\.?)?\s*([+-]?\d+(?:\.\d+)?)", text, re.IGNORECASE
    )
    gmp = gmp_match.group(1) if gmp_match else "N/A"

    return {
        "name": name,
        "open_date": open_date,
        "close_date": close_date,
        "price_band": price_band,
        "gmp": gmp,
    }


def get_upcoming_ipos() -> list[dict[str, Any]] | None:
    """
    Fetch upcoming IPO data from chittorgarh.com.

    Returns:
        List of up to 5 IPO dicts, or None on error.
    """
    try:
        response = requests.get(
            IPO_LIST_URL,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException:
        return None

    try:
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception:
        return None

    # Find IPO detail links: /ipo/company-name-ipo/1234/
    ipo_links: list[tuple[str, str]] = []
    seen_urls: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "")
        if ("chittorgarh.com/ipo/" in href or (href.startswith("/ipo/") and "-ipo/" in href)):
            if "/ipo/ipo_" in href or "ipo_list" in href:
                continue
            full_url = (
                href if href.startswith("http") else f"https://www.chittorgarh.com{href}"
            )
            if full_url in seen_urls:
                continue
            name = anchor.get_text(strip=True)
            if name and "IPO" in name and len(name) > 5:
                seen_urls.add(full_url)
                ipo_links.append((name, full_url))

    if not ipo_links:
        return []

    result: list[dict[str, Any]] = []
    for name, url in ipo_links[:MAX_IPOS]:
        ipo_data = _extract_ipo_from_detail_page(url, name)
        if ipo_data:
            result.append(ipo_data)

    return result if result else None
