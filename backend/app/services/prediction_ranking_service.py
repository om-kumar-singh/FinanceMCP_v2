"""
Prediction ranking engine.

Uses Advisor V2 `ensemble_forecast` to rank a basket of stocks by expected return.
No new data sources are introduced; this reuses existing yfinance-based services.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from app.services.advisor_v2.prediction_engine import ensemble_forecast
from app.services.stock_search_service import resolve_symbol


DEFAULT_PREDICTION_WATCHLIST: List[str] = [
    "RELIANCE.NS",
    "ICICIBANK.NS",
    "HDFCBANK.NS",
    "TCS.NS",
    "INFY.NS",
    "ITC.NS",
    "SBIN.NS",
    "KOTAKBANK.NS",
    "HCLTECH.NS",
    "TECHM.NS",
]


def _normalize_symbol(sym: str) -> Optional[str]:
    s = (sym or "").strip().upper()
    if not s:
        return None
    if s.endswith(".NS") or s.endswith(".BO") or s.startswith("^"):
        return s
    resolved = resolve_symbol(s)
    return resolved


def rank_by_expected_return(
    symbols: Optional[Iterable[str]] = None,
    *,
    horizon: str = "short",
    limit: int = 5,
) -> Dict[str, Any]:
    """
    Rank given symbols by Advisor V2 ensemble expected return.

    Returns:
    {
      "horizon": "short",
      "ranked": [
        {"symbol": "RELIANCE.NS", "expected_return": 0.034, "forecast": {...}},
        ...
      ]
    }
    """
    syms: List[str] = []
    seen = set()
    for s in symbols or DEFAULT_PREDICTION_WATCHLIST:
        norm = _normalize_symbol(s)
        if norm and norm not in seen:
            seen.add(norm)
            syms.append(norm)

    ranked: List[Dict[str, Any]] = []
    for s in syms:
        try:
            fc = ensemble_forecast(s, horizon=horizon)  # type: ignore[arg-type]
        except Exception:
            continue
        if not isinstance(fc, dict):
            continue
        er = fc.get("expected_return")
        if er is None:
            continue
        ranked.append(
            {
                "symbol": s,
                "expected_return": float(er),
            }
        )

    ranked.sort(key=lambda r: r["expected_return"], reverse=True)
    top = ranked[: max(1, min(limit, len(ranked)))]

    return {
        "horizon": horizon,
        "ranked": top,
    }

