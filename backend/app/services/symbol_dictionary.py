"""
Common company-name aliases -> yfinance symbols (India-focused).

Used by conversational parsing so queries like "HDFC Bank" resolve correctly.
"""

from __future__ import annotations

# Keys are lowercase match tokens/phrases.
# Keep entries conservative to avoid false positives.
COMMON_COMPANY_ALIASES: dict[str, str] = {
    "reliance": "RELIANCE.NS",
    "ril": "RELIANCE.NS",
    "tcs": "TCS.NS",
    "infosys": "INFY.NS",
    "infy": "INFY.NS",
    "hdfc bank": "HDFCBANK.NS",
    "hdfcbank": "HDFCBANK.NS",
    "hdfc": "HDFCBANK.NS",
    "icici bank": "ICICIBANK.NS",
    "icicibank": "ICICIBANK.NS",
    "icici": "ICICIBANK.NS",
    "sbi": "SBIN.NS",
    "state bank": "SBIN.NS",
    "itc": "ITC.NS",
    "wipro": "WIPRO.NS",
    "bharti airtel": "BHARTIARTL.NS",
    "airtel": "BHARTIARTL.NS",
    "kotak bank": "KOTAKBANK.NS",
    "kotak": "KOTAKBANK.NS",
    "l&t": "LT.NS",
    "lt": "LT.NS",
    "axis bank": "AXISBANK.NS",
    "axis": "AXISBANK.NS",
    "bajaj finance": "BAJFINANCE.NS",
    "maruti": "MARUTI.NS",
    "tata motors": "TATAMOTORS.NS",
    "hindustan unilever": "HINDUNILVR.NS",
    "hul": "HINDUNILVR.NS",
}

# Allowlist of 2-letter bare tickers that are valid in our domain
BARE_TOKEN_ALLOWLIST: set[str] = {"LT"}

