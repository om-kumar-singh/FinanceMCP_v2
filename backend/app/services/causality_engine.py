"""
Rule-based causality interpreter for cross-market signals.

This module consumes the output of `get_cross_market_signals()` and produces
human-readable causal insights (no ML).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _get_signal(signals: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
    v = signals.get(key)
    return v if isinstance(v, dict) else None


def _as_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def interpret_causality(signals: dict) -> list:
    """
    Interpret cross-market signals using fixed causal rules.

    Args:
        signals: dict returned by `get_cross_market_signals()`, containing keys:
                 us_10y_yield, wti_crude, usd_inr, gold, india_vix.

    Returns:
        List of insight objects. Empty list if no thresholds are crossed.
    """

    insights: List[Dict[str, Any]] = []

    # 1) US 10Y Bond Yield (^TNX)
    us10y = _get_signal(signals, "us_10y_yield")
    if us10y:
        direction = us10y.get("direction")
        change_pct = _as_float(us10y.get("change_pct"))
        current_value = _as_float(us10y.get("current_value"))
        if direction == "up" and change_pct is not None and change_pct > 0.5:
            insights.append(
                {
                    "signal_name": "us_10y_yield",
                    "current_value": current_value,
                    "change_pct": change_pct,
                    "impact": "Technology and growth stocks face valuation pressure",
                    "affected_sectors": ["IT", "Technology"],
                    "severity": "high" if change_pct > 1.0 else "medium",
                }
            )

    # 2) Crude Oil (WTI) (CL=F)
    crude = _get_signal(signals, "wti_crude")
    if crude:
        direction = crude.get("direction")
        change_pct = _as_float(crude.get("change_pct"))
        current_value = _as_float(crude.get("current_value"))
        if direction == "up" and change_pct is not None and change_pct > 1.0:
            insights.append(
                {
                    "signal_name": "wti_crude",
                    "current_value": current_value,
                    "change_pct": change_pct,
                    "impact": "Rising oil increases input costs, pressures aviation, paint, and logistics sectors",
                    "affected_sectors": ["Aviation", "Logistics", "Paints"],
                    "severity": "medium",
                }
            )

    # 3) USD/INR (USDINR=X) (INR weakening when USDINR goes up)
    usdinr = _get_signal(signals, "usd_inr")
    if usdinr:
        direction = usdinr.get("direction")
        change_pct = _as_float(usdinr.get("change_pct"))
        current_value = _as_float(usdinr.get("current_value"))
        if direction == "up" and change_pct is not None and change_pct > 0.3:
            # Spec requested benefited_sectors too; include it even though not required in object schema.
            insights.append(
                {
                    "signal_name": "usd_inr",
                    "current_value": current_value,
                    "change_pct": change_pct,
                    "impact": "Weaker INR benefits IT exporters but hurts oil importers",
                    "affected_sectors": ["IT", "Pharma"],
                    "benefited_sectors": ["IT", "Pharma"],
                    "severity": "low",
                }
            )

    # 4) India VIX (^INDIAVIX)
    vix = _get_signal(signals, "india_vix")
    if vix:
        direction = vix.get("direction")
        change_pct = _as_float(vix.get("change_pct"))
        current_value = _as_float(vix.get("current_value"))
        if direction == "up" and change_pct is not None and change_pct > 5.0:
            insights.append(
                {
                    "signal_name": "india_vix",
                    "current_value": current_value,
                    "change_pct": change_pct,
                    "impact": "High volatility signals market fear, broad market caution advised",
                    "affected_sectors": ["All"],
                    "severity": "high",
                }
            )

    # 5) Gold (GC=F)
    gold = _get_signal(signals, "gold")
    if gold:
        direction = gold.get("direction")
        change_pct = _as_float(gold.get("change_pct"))
        current_value = _as_float(gold.get("current_value"))
        if direction == "up" and change_pct is not None and change_pct > 0.5:
            insights.append(
                {
                    "signal_name": "gold",
                    "current_value": current_value,
                    "change_pct": change_pct,
                    "impact": "Gold rally suggests risk-off sentiment, defensive positioning preferred",
                    "affected_sectors": ["Banking", "FMCG"],
                    "severity": "low",
                }
            )

    return insights

