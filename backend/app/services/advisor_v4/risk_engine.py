"""
Advanced risk engine for Advisor V4.

Computes:
- Value at Risk (historical VaR)
- Expected shortfall (CVaR)
- Beta vs market index
- Portfolio volatility
- Drawdown risk
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from app.services.stock_service import get_stock_history


def _portfolio_return_series(weights: Dict[str, float], period: str = "1y") -> np.ndarray:
    symbols = list(weights.keys())
    if not symbols:
        return np.array([], dtype=float)

    from app.services.advisor_v4.portfolio_optimizer import _load_returns

    rets_map = _load_returns(symbols, period=period)
    if not rets_map:
        return np.array([], dtype=float)

    ordered = list(rets_map.keys())
    data = np.array([rets_map[s] for s in ordered], dtype=float)  # (n_assets, T)
    w = np.array([weights.get(s, 0.0) for s in ordered], dtype=float)
    if w.sum() == 0:
        w = np.repeat(1.0 / len(ordered), len(ordered))
    else:
        w = w / w.sum()

    return (w @ data).flatten()


def _index_series(index_symbol: str = "^NSEI", period: str = "1y") -> np.ndarray:
    try:
        from app.utils.yfinance_wrapper import fetch_history
    except Exception:
        return np.array([], dtype=float)

    try:
        hist = fetch_history(index_symbol, period=period, ttl=60)
    except Exception:
        return np.array([], dtype=float)

    if hist is None or hist.empty or len(hist) < 30:
        return np.array([], dtype=float)

    closes = hist["Close"]
    rets = closes.pct_change().dropna().values.astype(float)
    return rets


def compute_risk_metrics(weights: Dict[str, float]) -> Dict[str, Any]:
    """
    Compute portfolio-level risk metrics from weights and history.
    """
    series = _portfolio_return_series(weights, period="1y")
    if series.size == 0:
        return {
            "var_95": None,
            "expected_shortfall_95": None,
            "beta_vs_market": None,
            "volatility": None,
            "max_drawdown": None,
        }

    # Historical VaR / ES at 95%
    sorted_rets = np.sort(series)
    idx = int(0.05 * len(sorted_rets))
    var_95 = float(sorted_rets[idx])
    es_95 = float(sorted_rets[: idx + 1].mean()) if idx > 0 else var_95

    vol = float(series.std())

    # Max drawdown
    cum = (1.0 + series).cumprod()
    peak = np.maximum.accumulate(cum)
    dd = (cum - peak) / peak
    max_dd = float(dd.min()) if dd.size else 0.0

    # Beta vs index
    idx_rets = _index_series("^NSEI", period="1y")
    if idx_rets.size == 0 or idx_rets.size != series.size:
        beta = None
    else:
        cov = float(np.cov(series, idx_rets)[0, 1])
        var_mkt = float(np.var(idx_rets))
        beta = cov / var_mkt if var_mkt > 0 else None

    return {
        "var_95": round(var_95, 4),
        "expected_shortfall_95": round(es_95, 4),
        "beta_vs_market": None if beta is None else round(beta, 3),
        "volatility": round(vol, 4),
        "max_drawdown": round(max_dd, 4),
    }


def summarise_risk(weights: Dict[str, float]) -> Dict[str, Any]:
    """
    Provide a high-level risk score and category for the portfolio.
    """
    metrics = compute_risk_metrics(weights)

    vol = metrics.get("volatility") or 0.0
    max_dd = metrics.get("max_drawdown") or 0.0

    # Risk score heuristic: combine vol and drawdown magnitude.
    score = 0.0
    score += min(vol / 0.02, 2.0) * 30.0  # up to 60 pts
    score += min(abs(max_dd) / 0.2, 2.0) * 20.0  # up to 40 pts
    score = max(0.0, min(100.0, score))

    if score < 30:
        category = "low"
    elif score < 60:
        category = "medium"
    else:
        category = "high"

    return {
        "risk_score": round(score, 1),
        "risk_category": category,
        "risk_metrics": metrics,
    }

