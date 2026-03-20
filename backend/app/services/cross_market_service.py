"""
Cross-market macro signals service (yfinance).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.utils.yfinance_wrapper import fetch_history


_SIGNALS: Dict[str, str] = {
    "us_10y_yield": "^TNX",
    "wti_crude": "CL=F",
    "usd_inr": "USDINR=X",
    "gold": "GC=F",
    "india_vix": "^INDIAVIX",
}


def _safe_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _fetch_signal(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Fetch last two daily closes for a ticker and compute 1-day % change.

    Returns None on any failure.
    """
    try:
        hist = fetch_history(ticker, period="5d", interval="1d", ttl=60)
        if hist is None or hist.empty or "Close" not in hist:
            return None

        closes = hist["Close"].dropna()
        if len(closes) < 2:
            return None

        current_value = _safe_float(closes.iloc[-1])
        previous_value = _safe_float(closes.iloc[-2])
        if current_value is None or previous_value is None:
            return None

        if previous_value == 0:
            change_pct = None
            direction = None
        else:
            change_pct_raw = (current_value - previous_value) / previous_value * 100.0
            change_pct = float(round(change_pct_raw, 4))
            direction = "up" if change_pct_raw >= 0 else "down"

        return {
            "ticker": ticker,
            "current_value": current_value,
            "previous_value": previous_value,
            "change_pct": change_pct,
            "direction": direction,
        }
    except Exception:
        return None


def get_cross_market_signals() -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Fetch a bundle of cross-market macro signals.

    If an individual ticker fails, its value is None (does not crash the bundle).
    """
    result: Dict[str, Optional[Dict[str, Any]]] = {}
    for key, ticker in _SIGNALS.items():
        result[key] = _fetch_signal(ticker)
    return result

