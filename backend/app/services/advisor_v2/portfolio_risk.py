"""
Portfolio risk metrics for Advisor V2.

Builds on the existing `portfolio_service.analyze_portfolio` output to
compute volatility, an approximate Sharpe ratio, and a diversification
score, without changing any existing portfolio APIs.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.services.portfolio_service import analyze_portfolio
from app.services.stock_service import get_stock_history


def _compute_single_asset_volatility(symbol: str) -> float:
    """
    Estimate daily volatility from price history using existing history service.
    """
    hist = get_stock_history(symbol, period="6mo")
    if not hist or not hist.get("closes"):
        return 0.0
    closes = hist["closes"]
    if len(closes) < 10:
        return 0.0
    rets = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        curr = closes[i]
        if prev:
            rets.append((curr - prev) / prev)
    if len(rets) < 5:
        return 0.0
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / max(len(rets) - 1, 1)
    return float(var**0.5)


def _approximate_portfolio_risk(enriched_stocks: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Aggregate per‑asset volatilities using a simple weighted average.

    This intentionally ignores cross‑asset correlations to keep the
    implementation light‑weight and dependency‑free.
    """
    total_value = sum(s.get("current_value", 0.0) for s in enriched_stocks)
    if total_value <= 0:
        return {
            "volatility": 0.0,
            "sharpe": 0.0,
        }

    weighted_vol = 0.0
    for s in enriched_stocks:
        symbol = s.get("symbol")
        value = float(s.get("current_value", 0.0))
        if not symbol or value <= 0:
            continue
        w = value / total_value
        vol = _compute_single_asset_volatility(symbol)
        weighted_vol += w * vol

    total_pl = sum(s.get("profit_loss", 0.0) for s in enriched_stocks)
    invested = sum(s.get("invested_value", 0.0) for s in enriched_stocks)
    ret = (total_pl / invested) if invested else 0.0

    if weighted_vol <= 0:
        sharpe = 0.0
    else:
        sharpe = ret / (weighted_vol * (len(enriched_stocks) ** 0.5))

    return {
        "volatility": float(round(weighted_vol, 4)),
        "sharpe": float(round(sharpe, 3)),
    }


def _diversification_score(enriched_stocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    sectors = {}
    for s in enriched_stocks:
        sec = (s.get("sector") or "others").lower()
        sectors[sec] = sectors.get(sec, 0) + s.get("current_value", 0.0)

    total = sum(sectors.values()) or 1.0
    weights = {k: v / total for k, v in sectors.items()}

    # Herfindahl‑style index on sector weights
    hhi = sum(w * w for w in weights.values())
    # Transform into 0–100 diversification score (higher is better)
    score = max(0.0, min(100.0, (1.0 - hhi) * 125.0))

    # Simple concentration metric: max single‑name weight
    max_pos_wt = 0.0
    if total > 0:
        max_pos_wt = max((s.get("current_value", 0.0) / total for s in enriched_stocks), default=0.0)

    return {
        "diversification_score": float(round(score, 1)),
        "sector_weights": {k: round(v * 100.0, 2) for k, v in weights.items()},
        "max_position_weight_percent": float(round(max_pos_wt * 100.0, 2)),
    }


def analyse_portfolio_v2(stocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Wrapper around existing analyze_portfolio() with extra risk metrics.

    Input format is identical to /portfolio/analyze.
    """
    base = analyze_portfolio(stocks)
    if base.get("error"):
        return base

    enriched = base.get("stocks") or []
    risk = _approximate_portfolio_risk(enriched)
    div = _diversification_score(enriched)

    risk_metrics = {
        "volatility": risk["volatility"],
        "sharpe": risk["sharpe"],
        "diversification_score": div["diversification_score"],
        "max_position_weight_percent": div["max_position_weight_percent"],
        "sector_weights": div["sector_weights"],
    }

    return {
        "base": base,
        "risk_metrics": risk_metrics,
    }

