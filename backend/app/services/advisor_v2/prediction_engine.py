"""
Prediction engine for Advisor V2.

Provides light‑weight ensemble forecasts for stock returns by combining:
- A sequence-style model approximated from recent price momentum.
- A tree-style model approximated from technical indicator states.

This module deliberately reuses existing yfinance-based services
(`stock_service`) so we do not introduce new data sources.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional

from app.services.stock_service import (
    calculate_macd,
    calculate_moving_averages,
    calculate_rsi,
    get_stock_history,
)


Horizon = Literal["intraday", "short", "medium"]


@dataclass
class ModelForecast:
    expected_return: float  # fraction, e.g. 0.03 = +3%
    expected_volatility: float  # fraction, e.g. 0.20 = 20% annualised equivalent
    confidence: float  # 0–1


def _infer_horizon_days(horizon: Horizon) -> int:
    if horizon == "intraday":
        return 1
    if horizon == "short":
        return 5
    return 20


def _sequence_style_forecast(symbol: str, horizon: Horizon) -> Optional[ModelForecast]:
    """
    Approximate a sequence model by using recent price momentum.

    We look at recent closes from `get_stock_history` and fit a simple
    drift term; volatility is derived from daily returns.
    """
    hist = get_stock_history(symbol, period="6mo")
    if not hist or not hist.get("closes"):
        return None

    closes = hist["closes"]
    if len(closes) < 10:
        return None

    # Daily returns
    rets = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        curr = closes[i]
        if prev:
            rets.append((curr - prev) / prev)

    if len(rets) < 5:
        return None

    # Use recent 20 bars for drift/vol
    recent = rets[-20:]
    avg_ret = sum(recent) / len(recent)
    # Sample standard deviation
    mean = avg_ret
    var = sum((r - mean) ** 2 for r in recent) / max(len(recent) - 1, 1)
    sigma = var ** 0.5

    horizon_days = _infer_horizon_days(horizon)
    # Scale linearly for drift, sqrt for volatility
    exp_ret = avg_ret * horizon_days
    exp_vol = sigma * (horizon_days**0.5)

    # Confidence higher when we have more history and stable variance
    history_factor = min(len(rets) / 120.0, 1.0)
    variance_factor = 1.0 if sigma > 0 else 0.2
    confidence = max(0.1, min(history_factor * variance_factor, 1.0))

    return ModelForecast(
        expected_return=float(exp_ret),
        expected_volatility=float(exp_vol),
        confidence=float(confidence),
    )


def _tree_style_forecast(symbol: str, horizon: Horizon) -> Optional[ModelForecast]:
    """
    Approximate a tree model using technical indicator regimes.

    The idea: treat RSI, MACD, and moving averages as categorical
    features and map them to a coarse expected return / risk.
    """
    rsi = calculate_rsi(symbol)
    macd = calculate_macd(symbol)
    ma = calculate_moving_averages(symbol)

    if not (rsi or macd or ma):
        return None

    score = 0.0
    signals = 0

    if rsi:
        signals += 1
        sig = rsi.get("signal")
        val = float(rsi.get("rsi", 50))
        if sig == "oversold":
            score += 0.6
        elif sig == "overbought":
            score -= 0.6
        else:
            if 45 <= val <= 55:
                score += 0.1

    if macd:
        signals += 1
        trend = macd.get("trend")
        if trend == "bullish":
            score += 0.5
        elif trend == "bearish":
            score -= 0.5

    if ma:
        signals += 1
        if ma.get("signal_sma200") == "above":
            score += 0.4
        else:
            score -= 0.3

    if signals == 0:
        return None

    avg_signal_score = score / signals

    horizon_days = _infer_horizon_days(horizon)
    base_daily = 0.003 * avg_signal_score  # 0.3% * signal
    exp_ret = base_daily * horizon_days

    # Volatility heuristic: stronger signals imply taking more risk
    base_vol = 0.02 + abs(avg_signal_score) * 0.08
    exp_vol = base_vol * (horizon_days**0.5)

    confidence = min(0.3 + abs(avg_signal_score), 1.0)

    return ModelForecast(
        expected_return=float(exp_ret),
        expected_volatility=float(exp_vol),
        confidence=float(confidence),
    )


def ensemble_forecast(symbol: str, horizon: Horizon = "short") -> Dict[str, Any]:
    """
    Public API: get ensemble forecast for a stock.

    Returns a dict ready to embed under the Advisor V2 result:
    {
      "horizon": "short",
      "horizon_days": 5,
      "expected_return": ...,
      "expected_volatility": ...,
      "models": {
         "sequence": {...},
         "tree": {...}
      },
      "confidence": {...}
    }
    """
    horizon_days = _infer_horizon_days(horizon)

    seq = _sequence_style_forecast(symbol, horizon)
    tree = _tree_style_forecast(symbol, horizon)

    models: Dict[str, Any] = {}
    model_returns = []
    model_vols = []
    weights = []

    def _pack(name: str, mf: ModelForecast) -> None:
        models[name] = {
            "expected_return": round(mf.expected_return, 4),
            "expected_volatility": round(mf.expected_volatility, 4),
            "confidence": round(mf.confidence, 3),
        }
        model_returns.append(mf.expected_return)
        model_vols.append(mf.expected_volatility)
        weights.append(max(mf.confidence, 0.1))

    if seq:
        _pack("sequence", seq)
    if tree:
        _pack("tree", tree)

    if not models:
        return {
            "horizon": horizon,
            "horizon_days": horizon_days,
            "expected_return": None,
            "expected_volatility": None,
            "models": {},
            "confidence": {
                "score": 0.0,
                "label": "unknown",
            },
        }

    total_w = sum(weights) or 1.0
    w_ret = sum(r * w for r, w in zip(model_returns, weights)) / total_w
    w_vol = sum(v * w for v, w in zip(model_vols, weights)) / total_w

    avg_conf = sum(weights) / (len(weights) * 1.0)
    if avg_conf >= 0.75:
        label = "high"
    elif avg_conf >= 0.45:
        label = "medium"
    else:
        label = "low"

    return {
        "horizon": horizon,
        "horizon_days": horizon_days,
        "expected_return": round(float(w_ret), 4),
        "expected_volatility": round(float(w_vol), 4),
        "models": models,
        "confidence": {
            "score": round(float(avg_conf), 3),
            "label": label,
        },
    }

