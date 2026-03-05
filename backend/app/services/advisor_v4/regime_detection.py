"""
Market regime detection for Advisor V4.

Identifies coarse regimes such as:
- bull_market
- bear_market
- sideways_market
- high_volatility
- low_volatility

using only existing live data sources (NIFTY index via yfinance and
Advisor V2/V3 helpers).
"""

from __future__ import annotations

from typing import Any, Dict

import yfinance as yf


def detect_market_regime(index_symbol: str = "^NSEI") -> Dict[str, Any]:
    """
    Compute market regime using index trend and volatility.

    Output:
    {
      "market_regime": "bull_market" | "bear_market" | "sideways_market",
      "trend_strength": float 0–1,
      "volatility_level": "low_volatility" | "high_volatility" | "medium",
      "index_return_50d": float | null,
      "index_volatility_20d": float | null
    }
    """
    try:
        ticker = yf.Ticker(index_symbol)
        hist = ticker.history(period="6mo")
    except Exception:
        return {
            "market_regime": "sideways_market",
            "trend_strength": 0.5,
            "volatility_level": "medium",
            "index_return_50d": None,
            "index_volatility_20d": None,
        }

    if hist is None or hist.empty or len(hist) < 60:
        return {
            "market_regime": "sideways_market",
            "trend_strength": 0.5,
            "volatility_level": "medium",
            "index_return_50d": None,
            "index_volatility_20d": None,
        }

    closes = hist["Close"]
    latest = float(closes.iloc[-1])
    past_50 = float(closes.iloc[-51])
    ret_50d = (latest - past_50) / past_50 if past_50 else 0.0

    rets = closes.pct_change().dropna()
    recent = rets[-20:]
    if recent.empty:
        vol_20d = 0.0
    else:
        mean = float(recent.mean())
        var = float(((recent - mean) ** 2).sum() / max(len(recent) - 1, 1))
        vol_20d = var**0.5

    # Trend strength: scale +/-10% move over 50d into 0–1
    ts = 0.5 + ret_50d / 0.20
    ts = max(0.0, min(1.0, ts))

    if ret_50d > 0.05:
        market_regime = "bull_market"
    elif ret_50d < -0.05:
        market_regime = "bear_market"
    else:
        market_regime = "sideways_market"

    if vol_20d < 0.007:
        vol_label = "low_volatility"
    elif vol_20d > 0.02:
        vol_label = "high_volatility"
    else:
        vol_label = "medium"

    return {
        "market_regime": market_regime,
        "trend_strength": round(ts, 3),
        "volatility_level": vol_label,
        "index_return_50d": round(ret_50d, 4),
        "index_volatility_20d": round(vol_20d, 4),
    }

