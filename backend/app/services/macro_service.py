"""
Macroeconomic data service.
"""

from typing import Any

import requests

INFLATION_API = "https://api.worldbank.org/v2/country/IND/indicator/FP.CPI.TOTL.ZG"
GDP_API = "https://api.worldbank.org/v2/country/IND/indicator/NY.GDP.MKTP.KD.ZG"
REQUEST_TIMEOUT = 15


def get_repo_rate() -> dict[str, Any]:
    """
    Return latest RBI repo rate.

    Uses static value as RBI API is complex. Update periodically for accuracy.
    """
    return {
        "repo_rate": 6.5,
        "last_updated": "2025-01",
    }


def get_inflation() -> list[dict[str, Any]] | None:
    """
    Fetch India CPI inflation (annual %) from World Bank API.

    Returns last 3 years of inflation data, or None on error.
    """
    try:
        response = requests.get(
            f"{INFLATION_API}?format=json&per_page=10",
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError, IndexError):
        return None

    if not isinstance(data, list) or len(data) < 2:
        return None

    records = data[1]
    if not records:
        return None

    result = []
    for item in records:
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        date = item.get("date")
        if value is not None and date:
            result.append({
                "year": int(date),
                "inflation": round(float(value), 2),
            })

    result.sort(key=lambda x: x["year"], reverse=True)
    return result[:3]


def get_gdp() -> list[dict[str, Any]] | None:
    """
    Fetch India GDP growth (annual %) from World Bank API.

    Returns last 3 years of GDP growth data, or None on error.
    """
    try:
        response = requests.get(
            f"{GDP_API}?format=json&per_page=10",
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError, IndexError):
        return None

    if not isinstance(data, list) or len(data) < 2:
        return None

    records = data[1]
    if not records:
        return None

    result = []
    for item in records:
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        date = item.get("date")
        if value is not None and date:
            result.append({
                "year": int(date),
                "gdp_growth": round(float(value), 2),
            })

    result.sort(key=lambda x: x["year"], reverse=True)
    return result[:3]
