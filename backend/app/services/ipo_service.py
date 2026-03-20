"""
IPO tracking service using web scraping.
"""

import os
import re
from datetime import datetime
from typing import Any

import requests
from bs4 import BeautifulSoup

from app.utils.yfinance_wrapper import fetch_history, fetch_info

IPO_LIST_URL = os.getenv(
    "IPO_LIST_URL",
    "https://www.chittorgarh.com/ipo/ipo_list.asp",
)
IPO_PERFORMANCE_URL = os.getenv(
    "IPO_PERFORMANCE_URL",
    "https://www.chittorgarh.com/report/ipo-listing-performance-fy2025/93/",
)
GMP_URL = os.getenv(
    "GMP_URL",
    "https://www.investorgain.com/report/live-ipo-gmp/331/",
)
MAX_IPOS = int(os.getenv("IPO_MAX_COUNT", "5"))
REQUEST_TIMEOUT = int(os.getenv("IPO_REQUEST_TIMEOUT", "15"))
USER_AGENT = os.getenv("IPO_USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")


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

    # Lot size (market lot)
    lot_match = re.search(
        r"(?:Market Lot|Lot Size)\s*[:\s]+([\d,]+)", text, re.IGNORECASE
    )
    lot_size = lot_match.group(1).strip() if lot_match else "N/A"

    # Issue size in ₹ crores
    issue_match = re.search(
        r"Issue Size[^\d]*(?:[\u20b9₹]?\s*)?([\d.,]+)\s*(?:Cr|Crore|Crores?)",
        text,
        re.IGNORECASE,
    )
    issue_size = issue_match.group(1).strip() + " Cr" if issue_match else "N/A"

    # Listing date, if mentioned
    listing_match = re.search(
        r"Listing Date\s*([A-Za-z]+, [A-Za-z]+ \d+, \d{4})", text
    )
    listing_date = listing_match.group(1).strip() if listing_match else "N/A"

    # Subscription status based on open/close dates if possible
    subscription_status = "N/A"
    try:
        if open_date != "N/A" and close_date != "N/A":
            fmt = "%a, %b %d, %Y"
            open_dt = datetime.strptime(open_date, fmt).date()
            close_dt = datetime.strptime(close_date, fmt).date()
            from app.utils.datetime_utils import get_ist_now
            today = get_ist_now().date()
            if today < open_dt:
                subscription_status = "upcoming"
            elif open_dt <= today <= close_dt:
                subscription_status = "open"
            else:
                subscription_status = "closed"
    except Exception:
        subscription_status = "N/A"

    return {
        "name": name,
        "open_date": open_date,
        "close_date": close_date,
        "price_band": price_band,
        "gmp": gmp,
        "subscription_status": subscription_status,
        "lot_size": lot_size,
        "issue_size": issue_size,
        "listing_date": listing_date,
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


def get_gmp(ipo_name: str | None = None) -> Any:
    """
    Fetch live IPO GMP data from investorgain.com.

    Args:
        ipo_name: Optional IPO name filter (partial, case-insensitive).

    Returns:
        List of dicts with GMP data, or an error dict on failure.
    """
    try:
        response = requests.get(
            GMP_URL,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException:
        return {
            "error": "GMP data temporarily unavailable",
            "suggestion": "Try visiting https://www.investorgain.com directly",
        }

    try:
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception:
        return {
            "error": "GMP data temporarily unavailable",
            "suggestion": "Try visiting https://www.investorgain.com directly",
        }

    tables = soup.find_all("table")
    target_table = None
    for table in tables:
        header_row = table.find("tr")
        if not header_row:
            continue
        headers = [th.get_text(strip=True).lower() for th in header_row.find_all("th")]
        header_text = " ".join(headers)
        if "ipo" in header_text and "gmp" in header_text:
            target_table = table
            break

    if target_table is None:
        return {
            "error": "GMP data temporarily unavailable",
            "suggestion": "Try visiting https://www.investorgain.com directly",
        }

    rows = target_table.find_all("tr")[1:]
    results: list[dict[str, Any]] = []

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 4:
            continue
        try:
            name_text = cols[0].get_text(strip=True)
            gmp_text = cols[1].get_text(" ", strip=True)
            issue_text = cols[2].get_text(" ", strip=True)
            updated_text = cols[-1].get_text(" ", strip=True)

            name_clean = name_text.replace("IPO", "").strip()

            # Extract numeric values
            gmp_price = 0.0
            gmp_price_match = re.search(r"([+-]?\d+(?:\.\d+)?)", gmp_text)
            if gmp_price_match:
                gmp_price = float(gmp_price_match.group(1))

            issue_price = 0.0
            issue_match = re.search(r"(\d+(?:\.\d+)?)", issue_text.replace(",", ""))
            if issue_match:
                issue_price = float(issue_match.group(1))

            estimated_listing = issue_price + gmp_price if issue_price else 0.0
            gmp_percent = (
                round((gmp_price / issue_price) * 100, 2) if issue_price else 0.0
            )

            item = {
                "ipo_name": name_clean,
                "gmp_price": gmp_price,
                "gmp_percent": gmp_percent,
                "issue_price": issue_price,
                "estimated_listing": estimated_listing,
                "last_updated": updated_text or "N/A",
            }
            results.append(item)
        except Exception:
            continue

    if ipo_name:
        q = ipo_name.lower()
        results = [r for r in results if q in r.get("ipo_name", "").lower()]

    return results[:10]


def get_sme_stock_analysis(symbol: str) -> dict[str, Any] | None:
    """
    Analyze SME stock using yfinance.

    Args:
        symbol: SME stock symbol (e.g., ABCSME.NS or ABCSME.BO)

    Returns:
        Dict with price, 52W range, market cap, valuation, volumes, and category.
    """
    if not symbol or not str(symbol).strip():
        return None

    symbol = str(symbol).strip().upper()

    try:
        hist = fetch_history(symbol, period="1y", ttl=600)
    except Exception:
        return None

    if hist is None or hist.empty or len(hist) < 2:
        return None

    latest = hist.iloc[-1]
    prev = hist.iloc[-2]

    price = float(latest["Close"])
    prev_close = float(prev["Close"])
    change = price - prev_close
    change_percent = (change / prev_close) * 100 if prev_close else 0.0

    high_52w = float(hist["High"].max())
    low_52w = float(hist["Low"].min())

    price_vs_52w_high = (
        ((high_52w - price) / high_52w) * 100 if high_52w else 0.0
    )
    price_vs_52w_low = (
        ((price - low_52w) / low_52w) * 100 if low_52w else 0.0
    )

    avg_volume = float(hist["Volume"].mean()) if "Volume" in hist else 0.0
    today_volume = float(latest["Volume"]) if "Volume" in latest else 0.0

    info: dict[str, Any] = fetch_info(symbol, ttl=600) or {}

    market_cap = info.get("marketCap") or info.get("market_cap") or 0
    company_name = info.get("longName") or info.get("shortName") or symbol
    sector = info.get("sector") or ""
    industry = info.get("industry") or ""
    pe_ratio = info.get("trailingPE") or info.get("forwardPE") or None

    # Market cap category in ₹ crores
    category = "N/A"
    if market_cap and isinstance(market_cap, (int, float)):
        cap_crore = market_cap / 1e7  # 1 crore = 10,000,000
        if cap_crore < 500:
            category = "Micro Cap SME"
        elif cap_crore <= 2000:
            category = "Small Cap SME"
        else:
            category = "Mid Cap SME"

    return {
        "symbol": symbol,
        "company_name": company_name,
        "sector": sector,
        "industry": industry,
        "price": round(price, 2),
        "change": round(change, 2),
        "change_percent": round(change_percent, 2),
        "high_52w": round(high_52w, 2),
        "low_52w": round(low_52w, 2),
        "price_vs_52w_high": round(price_vs_52w_high, 2),
        "price_vs_52w_low": round(price_vs_52w_low, 2),
        "market_cap": market_cap,
        "pe_ratio": pe_ratio,
        "avg_volume": round(avg_volume, 2),
        "today_volume": today_volume,
        "sme_category": category,
    }


def get_ipo_performance(limit: int = 10) -> list[dict[str, Any]] | None:
    """
    Fetch recent IPO listing performance data from chittorgarh.com.

    Args:
        limit: Number of IPOs to return.

    Returns:
        List of IPO performance dicts, or None on error.
    """
    try:
        response = requests.get(
            IPO_PERFORMANCE_URL,
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

    tables = soup.find_all("table")
    target_table = None
    for table in tables:
        header_row = table.find("tr")
        if not header_row:
            continue
        headers = [th.get_text(strip=True).lower() for th in header_row.find_all("th")]
        header_text = " ".join(headers)
        if "company name" in header_text and "listing date" in header_text:
            target_table = table
            break

    if target_table is None:
        return None

    rows = target_table.find_all("tr")[1:]
    results: list[dict[str, Any]] = []

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 5:
            continue

        try:
            company_name = cols[0].get_text(strip=True)
            listing_date_text = cols[1].get_text(strip=True)
            issue_price_text = cols[2].get_text(strip=True)
            listing_price_text = cols[3].get_text(strip=True)
            current_price_text = cols[4].get_text(strip=True)

            # Parse prices
            def _to_float(value: str) -> float:
                m = re.search(r"(\d+(?:\.\d+)?)", value.replace(",", ""))
                return float(m.group(1)) if m else 0.0

            issue_price = _to_float(issue_price_text)
            listing_price = _to_float(listing_price_text)
            current_price = _to_float(current_price_text)

            listing_gain_percent = (
                ((listing_price - issue_price) / issue_price) * 100
                if issue_price
                else 0.0
            )
            current_gain_percent = (
                ((current_price - issue_price) / issue_price) * 100
                if issue_price and current_price
                else 0.0
            )

            # Parse listing date for sorting
            sort_date = None
            try:
                sort_date = datetime.strptime(listing_date_text, "%d-%b-%Y").date()
            except Exception:
                try:
                    sort_date = datetime.strptime(
                        listing_date_text, "%d %b %Y"
                    ).date()
                except Exception:
                    sort_date = None

            results.append(
                {
                    "company_name": company_name,
                    "listing_date": listing_date_text,
                    "issue_price": issue_price,
                    "listing_price": listing_price,
                    "listing_gain_percent": round(listing_gain_percent, 2),
                    "current_price": current_price or None,
                    "current_gain_percent": round(current_gain_percent, 2)
                    if current_price
                    else None,
                    "_sort_date": sort_date,
                }
            )
        except Exception:
            continue

    if not results:
        return None

    # Sort by listing_date descending when available
    results.sort(
        key=lambda x: x.get("_sort_date") or datetime.min.date(),
        reverse=True,
    )

    trimmed = results[: max(1, min(limit, len(results)))]
    for item in trimmed:
        item.pop("_sort_date", None)

    return trimmed
