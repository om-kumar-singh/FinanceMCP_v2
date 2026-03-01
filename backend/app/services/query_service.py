"""
Rule-based query processing for financial questions.
"""

import re
from typing import Any

from app.services.ipo_service import get_upcoming_ipos
from app.services.macro_service import get_gdp, get_inflation, get_repo_rate
from app.services.mutual_fund_service import calculate_sip, get_mutual_fund_nav

# Stock name to symbol mapping (NSE)
STOCK_SYMBOLS = {
    "reliance": "RELIANCE.NS",
    "reli": "RELIANCE.NS",
    "tcs": "TCS.NS",
    "infosys": "INFY.NS",
    "infy": "INFY.NS",
    "hdfc": "HDFCBANK.NS",
    "hdfc bank": "HDFCBANK.NS",
    "hdfcbank": "HDFCBANK.NS",
    "sbi": "SBIN.NS",
    "icici": "ICICIBANK.NS",
    "icici bank": "ICICIBANK.NS",
    "bharti": "BHARTIARTL.NS",
    "airtel": "BHARTIARTL.NS",
    "itc": "ITC.NS",
    "kotak": "KOTAKBANK.NS",
    "kotak bank": "KOTAKBANK.NS",
    "lt": "LT.NS",
    "larsen": "LT.NS",
    "asian paint": "ASIANPAINT.NS",
    "asianpaint": "ASIANPAINT.NS",
    "maruti": "MARUTI.NS",
    "tata": "TATAMOTORS.NS",
    "tata motors": "TATAMOTORS.NS",
}
DEFAULT_STOCK = "RELIANCE.NS"
DEFAULT_SCHEME_CODE = "119551"


def _extract_stock_symbol(query: str) -> str:
    """Extract stock symbol from query using keyword matching."""
    q = query.lower()
    for name, symbol in sorted(STOCK_SYMBOLS.items(), key=lambda x: -len(x[0])):
        if name in q:
            return symbol
    # Check for symbol pattern like RELIANCE.NS or TCS.NS
    match = re.search(r"\b([A-Z]{2,10}\.NS)\b", query, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return DEFAULT_STOCK


def _extract_scheme_code(query: str) -> str:
    """Extract mutual fund scheme code from query."""
    match = re.search(r"\b(\d{5,6})\b", query)
    return match.group(1) if match else DEFAULT_SCHEME_CODE


def _extract_sip_params(query: str) -> tuple[float, int, float]:
    """Extract SIP params: monthly_investment, years, annual_return."""
    numbers = re.findall(r"\b(\d+(?:\.\d+)?)\b", query)
    nums = [float(n) for n in numbers]
    monthly = 5000.0
    years = 10
    annual = 12.0
    if len(nums) >= 1:
        monthly = nums[0]
    if len(nums) >= 2:
        years = int(nums[1])
    if len(nums) >= 3:
        annual = nums[2]
    # Check for percentage
    pct_match = re.search(r"(\d+(?:\.\d+)?)\s*%", query)
    if pct_match:
        annual = float(pct_match.group(1))
    return (monthly, years, annual)


def process_query(query: str) -> dict[str, Any]:
    """
    Process natural language financial query using rule-based intent detection.

    Returns:
        Dict with query, result, source on success; or message on no match.
    """
    if not query or not str(query).strip():
        return {"message": "Sorry, I could not understand the query"}

    q = str(query).strip().lower()

    # SIP: "sip" keyword
    if "sip" in q:
        monthly, years, annual = _extract_sip_params(query)
        result = calculate_sip(monthly, years, annual)
        return {"query": query, "result": result, "source": "sip"}

    # RSI: "rsi" keyword
    if "rsi" in q:
        from app.services.stock_service import calculate_rsi

        symbol = _extract_stock_symbol(query)
        result = calculate_rsi(symbol)
        if result is None:
            return {"query": query, "result": {"error": f"No RSI data for {symbol}"}, "source": "rsi"}
        return {"query": query, "result": result, "source": "rsi"}

    # MACD: "macd" keyword
    if "macd" in q:
        from app.services.stock_service import calculate_macd

        symbol = _extract_stock_symbol(query)
        result = calculate_macd(symbol)
        if result is None:
            return {"query": query, "result": {"error": f"No MACD data for {symbol}"}, "source": "macd"}
        return {"query": query, "result": result, "source": "macd"}

    # MUTUAL FUND: "mutual fund" or "nav"
    if "mutual fund" in q or ("nav" in q and "mutual" not in q):
        scheme_code = _extract_scheme_code(query)
        result = get_mutual_fund_nav(scheme_code)
        if result is None:
            return {"query": query, "result": {"error": f"No NAV data for scheme {scheme_code}"}, "source": "mutual_fund"}
        return {"query": query, "result": result, "source": "mutual_fund"}

    # IPO: "ipo" keyword
    if "ipo" in q:
        result = get_upcoming_ipos()
        if result is None:
            return {"query": query, "result": {"error": "Unable to fetch IPO data"}, "source": "ipo"}
        return {"query": query, "result": result, "source": "ipo"}

    # MACRO: repo, inflation, gdp
    if "repo" in q:
        result = get_repo_rate()
        return {"query": query, "result": result, "source": "macro"}
    if "inflation" in q:
        result = get_inflation()
        if result is None:
            return {"query": query, "result": {"error": "Unable to fetch inflation data"}, "source": "macro"}
        return {"query": query, "result": result, "source": "macro"}
    if "gdp" in q:
        result = get_gdp()
        if result is None:
            return {"query": query, "result": {"error": "Unable to fetch GDP data"}, "source": "macro"}
        return {"query": query, "result": result, "source": "macro"}

    # STOCK: price, stock, share
    if any(w in q for w in ("price", "stock", "share", "quote")):
        from app.services.stock_service import get_stock_quote

        symbol = _extract_stock_symbol(query)
        result = get_stock_quote(symbol)
        if result is None:
            return {"query": query, "result": {"error": f"No data for {symbol}"}, "source": "stock_api"}
        return {"query": query, "result": result, "source": "stock_api"}

    return {"message": "Sorry, I could not understand the query"}
