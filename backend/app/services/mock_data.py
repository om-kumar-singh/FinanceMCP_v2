"""
Mock/fallback data generators used when external market APIs fail.
The goal is: UI never breaks, and repeated calls still look realistic.
"""

from __future__ import annotations

import time
from typing import Any


_MOCK_NEWS_POOL: dict[str, list[dict[str, Any]]] = {
    "NSE": [
        {"title": "Nifty ends higher as banking and IT stocks gain", "source": "Economic Times"},
        {"title": "RBI commentary supports sentiment; rate-sensitive stocks rally", "source": "Business Standard"},
        {"title": "Midcaps outperform; breadth improves across sectors", "source": "Moneycontrol"},
        {"title": "FII inflows pick up; rupee stable amid global cues", "source": "Livemint"},
        {"title": "PSU banks lead; volatility cools after choppy open", "source": "CNBC-TV18"},
        {"title": "Energy and metals mixed; defensives see selective buying", "source": "Reuters"},
        {"title": "Nifty holds key support; traders watch global yields", "source": "The Hindu BusinessLine"},
        {"title": "Auto stocks advance on demand optimism; broader market steady", "source": "Financial Express"},
        {"title": "IT recovers; deal wins and rupee moves in focus", "source": "Economic Times"},
        {"title": "Bank Nifty strength offsets FMCG drag; market closes green", "source": "Moneycontrol"},
        {"title": "Earnings updates drive stock-specific action; indices inch up", "source": "Business Standard"},
        {"title": "Market participants track crude, USDINR; risk-on tone persists", "source": "Livemint"},
    ],
    "BSE": [
        {"title": "Sensex rises as financials support broader sentiment", "source": "Economic Times"},
        {"title": "Defensive pockets steady; select cyclicals push Sensex up", "source": "Business Standard"},
        {"title": "Traders watch global cues; Sensex gains in late trade", "source": "Moneycontrol"},
        {"title": "FII flows and rupee trend keep focus on largecaps", "source": "Livemint"},
        {"title": "Volatility remains contained; Sensex ends in the green", "source": "CNBC-TV18"},
        {"title": "Metals mixed; banks firm; Sensex posts modest gains", "source": "Reuters"},
        {"title": "Earnings and guidance drive rotation across sectors", "source": "The Hindu BusinessLine"},
        {"title": "Broader market improves; select heavyweights lift indices", "source": "Financial Express"},
    ],
}


def sample_mock_news(market: str = "NSE", k: int = 5) -> dict[str, Any]:
    """
    Return varied mock headlines. Uses time-based jitter so repeated calls
    are not identical (e.g., user types \"one more\" multiple times).
    """
    m = (market or "NSE").strip().upper()
    pool = _MOCK_NEWS_POOL.get(m) or _MOCK_NEWS_POOL["NSE"]

    # Time-based jitter: changes every call, low collision.
    # Keep it deterministic enough for a single response.
    n = len(pool)
    if n == 0:
        return {"news": [], "summary": "Market update: headlines unavailable.", "market": m}

    # Create a rotating window based on current time
    idx = int((time.time_ns() // 1_000_000) % n)
    k = max(1, min(int(k or 5), min(8, n)))
    news = [pool[(idx + i) % n] for i in range(k)]

    summary = f"{m} Market Update: {news[0]['title']}" if news else f"{m} Market Update"
    return {"news": news, "summary": summary, "market": m}

