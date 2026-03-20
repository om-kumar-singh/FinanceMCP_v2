"""
Market context analysis for Advisor V3.

Provides a lightweight view of:
- overall market regime (bullish / neutral / bearish)
- sector strength for the symbol's sector
- volatility regime based on index behaviour
"""

from __future__ import annotations

from typing import Any, Dict

from app.services.sector_service import SECTOR_STOCKS, get_sector_performance


def _infer_symbol_sector(symbol: str) -> str:
    """
    Map a symbol to one of the coarse sectors defined in SECTOR_STOCKS.
    Falls back to "others" if not found.
    """
    s = symbol.upper()
    for sector, symbols in SECTOR_STOCKS.items():
        if s in symbols:
            return sector
    return "others"


def _index_context(index_symbol: str = "^NSEI") -> Dict[str, Any]:
    """
    Use NIFTY index history to estimate market trend and volatility regime.
    """
    try:
        from app.utils.yfinance_wrapper import fetch_history

        hist = fetch_history(index_symbol, period="3mo", ttl=60)
    except Exception:
        return {
            "market_regime": "unknown",
            "market_volatility_level": "unknown",
            "index_return_20d": None,
            "index_volatility_20d": None,
        }

    if hist is None or hist.empty or len(hist) < 22:
        return {
            "market_regime": "unknown",
            "market_volatility_level": "unknown",
            "index_return_20d": None,
            "index_volatility_20d": None,
        }

    closes = hist["Close"]
    latest = float(closes.iloc[-1])
    past = float(closes.iloc[-21])
    ret_20d = (latest - past) / past if past else 0.0

    # Daily returns for vol
    rets = closes.pct_change().dropna()
    recent = rets[-20:]
    if recent.empty:
        vol_20d = 0.0
    else:
        mean = float(recent.mean())
        var = float(((recent - mean) ** 2).sum() / max(len(recent) - 1, 1))
        vol_20d = var**0.5

    if ret_20d > 0.05:
        regime = "bullish"
    elif ret_20d < -0.05:
        regime = "bearish"
    else:
        regime = "neutral"

    if vol_20d < 0.008:
        vol_regime = "low"
    elif vol_20d < 0.018:
        vol_regime = "medium"
    else:
        vol_regime = "high"

    return {
        "market_regime": regime,
        "market_volatility_level": vol_regime,
        "index_return_20d": round(ret_20d, 4),
        "index_volatility_20d": round(vol_20d, 4),
    }


def get_market_context(symbol: str) -> Dict[str, Any]:
    """
    Public API for Advisor V3.

    Returns:
    {
      "market_regime": "bullish" | "neutral" | "bearish" | "unknown",
      "market_volatility_level": "low" | "medium" | "high" | "unknown",
      "sector": "banking" | "it" | ... | "others",
      "sector_strength_score": float | null,
      "sector_sentiment": str | null,
      "index_return_20d": float | null,
      "index_volatility_20d": float | null
    }
    """
    index_info = _index_context("^NSEI")
    sector = _infer_symbol_sector(symbol)

    sector_strength_score = None
    sector_sentiment = None
    if sector != "others":
        data = get_sector_performance(sector)
        if not data.get("error"):
            sector_strength_score = float(data.get("sector_avg_day_change") or 0.0)
            sector_sentiment = data.get("sentiment")

    return {
        "market_regime": index_info["market_regime"],
        "market_volatility_level": index_info["market_volatility_level"],
        "sector": sector,
        "sector_strength_score": sector_strength_score,
        "sector_sentiment": sector_sentiment,
        "index_return_20d": index_info["index_return_20d"],
        "index_volatility_20d": index_info["index_volatility_20d"],
    }

