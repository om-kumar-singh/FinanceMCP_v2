"""
Cross-market macro signals routes.
"""

from fastapi import APIRouter

from app.services.cross_market_service import get_cross_market_signals
from app.utils.datetime_utils import get_ist_timestamp
from app.services.causality_engine import interpret_causality


cross_market_router = APIRouter(prefix="/cross-market", tags=["cross-market"])


@cross_market_router.get("/signals")
def cross_market_signals():
    signals = get_cross_market_signals()
    return {**signals, "data_timestamp": get_ist_timestamp()}


@cross_market_router.get("/analysis")
def cross_market_analysis():
    signals = get_cross_market_signals()
    insights = interpret_causality(signals)

    # Remap keys to the API response contract (without changing the underlying signal fetcher).
    key_map = {
        "bond_yield": "us_10y_yield",
        "crude_oil": "wti_crude",
        "usd_inr": "usd_inr",
        "gold": "gold",
        "india_vix": "india_vix",
    }

    remapped_signals = {out_k: signals.get(in_k) for out_k, in_k in key_map.items()}

    return {
        "signals": remapped_signals,
        "causal_insights": insights,
        "insight_count": len(insights),
        "data_timestamp": get_ist_timestamp(),
    }

