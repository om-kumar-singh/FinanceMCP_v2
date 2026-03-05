"""
Smart money / institutional flow detection for Advisor V4.

Uses existing price and volume data to infer:
- accumulation
- distribution
- neutral / mixed flows
"""

from __future__ import annotations

from typing import Any, Dict

from app.services.stock_service import get_stock_history


def detect_smart_money(symbol: str) -> Dict[str, Any]:
    """
    Estimate institutional activity from volume spikes and price moves.
    """
    hist = get_stock_history(symbol, period="3mo")
    if not hist or not hist.get("closes") or not hist.get("volumes"):
        return {
            "institutional_activity": "unknown",
            "confidence": 0.3,
            "volume_zscore": None,
            "price_change": None,
        }

    closes = hist["closes"]
    vols = hist["volumes"]
    if len(closes) < 20 or len(vols) < 20:
        return {
            "institutional_activity": "unknown",
            "confidence": 0.3,
            "volume_zscore": None,
            "price_change": None,
        }

    last_close = float(closes[-1])
    prev_close = float(closes[-2])
    price_change = (last_close - prev_close) / prev_close if prev_close else 0.0

    recent_vols = vols[-20:]
    mean_vol = float(sum(recent_vols) / len(recent_vols))
    var = sum((v - mean_vol) ** 2 for v in recent_vols) / max(len(recent_vols) - 1, 1)
    std_vol = var**0.5
    last_vol = float(vols[-1])

    if std_vol > 0:
        z = (last_vol - mean_vol) / std_vol
    else:
        z = 0.0

    # Simple rules:
    # - Large positive z and positive price move -> accumulation
    # - Large positive z and negative price move -> distribution
    # - Otherwise neutral
    if z > 2.0 and price_change > 0.02:
        activity = "institutional_buying"
        conf = 0.75
    elif z > 2.0 and price_change < -0.02:
        activity = "distribution"
        conf = 0.75
    elif z > 1.0 and abs(price_change) > 0.01:
        activity = "accumulation_phase"
        conf = 0.6
    else:
        activity = "neutral"
        conf = 0.45

    return {
        "institutional_activity": activity,
        "confidence": round(conf, 3),
        "volume_zscore": round(z, 2),
        "price_change": round(price_change, 4),
    }

