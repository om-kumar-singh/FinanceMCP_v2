"""
AI Portfolio Optimizer for Advisor V4.

Implements a lightweight Markowitz-style optimizer on top of existing
price history services (no new data sources).
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from app.services.stock_service import get_stock_history


def _load_returns(symbols: List[str], period: str = "1y") -> Dict[str, List[float]]:
    """
    Load daily returns for each symbol using existing history service.
    """
    series: Dict[str, List[float]] = {}
    max_len = 0
    for s in symbols:
        hist = get_stock_history(s, period=period)
        closes = (hist or {}).get("closes") or []
        if len(closes) < 30:
            continue
        rets = []
        for i in range(1, len(closes)):
            prev = closes[i - 1]
            curr = closes[i]
            if prev:
                rets.append((curr - prev) / prev)
        if len(rets) >= 20:
            series[s] = rets
            max_len = max(max_len, len(rets))

    # Align last max_len observations for each series
    aligned: Dict[str, List[float]] = {}
    for s, rets in series.items():
        if len(rets) > max_len:
            aligned[s] = rets[-max_len:]
        elif len(rets) < max_len:
            # Pad at front with zeros to keep alignment simple
            aligned[s] = [0.0] * (max_len - len(rets)) + rets
        else:
            aligned[s] = rets
    return aligned


def optimize_portfolio(
    symbols: List[str],
    *,
    risk_aversion: float = 3.0,
) -> Dict[str, Any]:
    """
    Approximate mean-variance optimal weights using historical returns.

    Returns:
    {
      "weights": { "RELIANCE.NS": 0.2, ... },
      "expected_return": float,
      "volatility": float,
      "sharpe_ratio": float,
      "sortino_ratio": float,
      "max_drawdown": float,
      "diversification_score": float
    }
    """
    if not symbols:
        return {
            "weights": {},
            "expected_return": None,
            "volatility": None,
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "max_drawdown": None,
            "diversification_score": None,
        }

    rets_map = _load_returns(symbols, period="1y")
    if not rets_map:
        return {
            "weights": {s: 1.0 / len(symbols) for s in symbols},
            "expected_return": None,
            "volatility": None,
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "max_drawdown": None,
            "diversification_score": None,
        }

    ordered = list(rets_map.keys())
    data = np.array([rets_map[s] for s in ordered], dtype=float)  # shape (n_assets, T)
    if data.shape[1] < 20:
        return {
            "weights": {s: 1.0 / len(ordered) for s in ordered},
            "expected_return": None,
            "volatility": None,
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "max_drawdown": None,
            "diversification_score": None,
        }

    mean_rets = data.mean(axis=1)  # daily expected return
    cov = np.cov(data)

    n = len(ordered)
    ones = np.ones(n)

    try:
        inv_cov = np.linalg.pinv(cov)
    except Exception:
        inv_cov = np.eye(n)

    # Max Sharpe weights with risk_aversion scaling
    # w ∝ Σ^{-1} μ
    raw = inv_cov @ mean_rets
    raw = np.maximum(raw, 0)  # long-only
    if raw.sum() <= 0:
        w = np.repeat(1.0 / n, n)
    else:
        w = raw / raw.sum()

    port_ret = float(w @ mean_rets)
    port_vol = float(np.sqrt(w @ cov @ w))

    if port_vol > 0:
        sharpe = port_ret / port_vol
    else:
        sharpe = 0.0

    # Sortino: use downside deviation
    port_series = (w @ data).flatten()
    downside = port_series[port_series < 0]
    if len(downside) > 0:
        dd = float(np.sqrt((downside**2).mean()))
        sortino = port_ret / dd if dd > 0 else 0.0
    else:
        sortino = sharpe

    # Max drawdown on cumulative curve
    cum = (1.0 + port_series).cumprod()
    peak = np.maximum.accumulate(cum)
    dd_series = (cum - peak) / peak
    max_dd = float(dd_series.min()) if len(dd_series) else 0.0

    # Diversification via Herfindahl index on weights
    hhi = float((w**2).sum())
    div_score = max(0.0, min(1.0, (1.0 - hhi) * 1.25))

    weights = {sym: float(round(wt, 4)) for sym, wt in zip(ordered, w)}

    return {
        "weights": weights,
        "expected_return": round(port_ret, 5),
        "volatility": round(port_vol, 5),
        "sharpe_ratio": round(sharpe, 3),
        "sortino_ratio": round(sortino, 3),
        "max_drawdown": round(max_dd, 4),
        "diversification_score": round(div_score * 100.0, 1),
    }

