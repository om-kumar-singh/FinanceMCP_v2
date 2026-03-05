"""
Signal scoring for Advisor V2.

Combines ensemble forecasts with technical indicators to produce a
normalized 0–100 signal score and coarse action label suitable for
the existing advisor response pattern.
"""

from __future__ import annotations

from typing import Any, Dict, Literal

from app.services.advisor_v2.prediction_engine import Horizon, ensemble_forecast
from app.services.stock_service import (
    calculate_bollinger_bands,
    calculate_macd,
    calculate_moving_averages,
    calculate_rsi,
    get_stock_detail,
)


Action = Literal["strong_buy", "buy", "hold", "reduce", "avoid"]


def _score_from_forecast(forecast: Dict[str, Any]) -> float:
    exp_ret = forecast.get("expected_return")
    exp_vol = forecast.get("expected_volatility")
    conf = (forecast.get("confidence") or {}).get("score", 0.0)
    if exp_ret is None or exp_vol in (None, 0):
        return 50.0

    # Simple reward-to-risk style metric scaled into 0–100
    rr = float(exp_ret) / max(abs(float(exp_vol)), 1e-6)
    raw = 50.0 + rr * 20.0
    # compress extremes
    raw = max(0.0, min(100.0, raw))

    # Confidence-weighted pull towards neutral
    return (50.0 * (1.0 - conf)) + (raw * conf)


def _score_from_technicals(symbol: str) -> Dict[str, Any]:
    rsi = calculate_rsi(symbol)
    macd = calculate_macd(symbol)
    ma = calculate_moving_averages(symbol)
    bb = calculate_bollinger_bands(symbol)

    score = 50.0
    details = []

    if rsi:
        val = float(rsi.get("rsi", 50))
        sig = rsi.get("signal")
        if sig == "oversold":
            score += 10
            details.append(f"RSI {val:.1f} oversold")
        elif sig == "overbought":
            score -= 10
            details.append(f"RSI {val:.1f} overbought")
        else:
            details.append(f"RSI {val:.1f} neutral")

    if macd:
        trend = macd.get("trend")
        if trend == "bullish":
            score += 8
            details.append("MACD bullish")
        elif trend == "bearish":
            score -= 8
            details.append("MACD bearish")

    if ma:
        if ma.get("signal_sma200") == "above":
            score += 6
            details.append("Price above 200‑day MA")
        else:
            score -= 6
            details.append("Price below 200‑day MA")

    if bb:
        sig = bb.get("signal")
        if sig == "oversold":
            score += 4
            details.append("Price near lower Bollinger band")
        elif sig == "overbought":
            score -= 4
            details.append("Price near upper Bollinger band")

    score = max(0.0, min(100.0, score))
    return {"score": score, "details": details, "indicators": {"rsi": rsi, "macd": macd, "moving_averages": ma, "bollinger": bb}}


def _action_from_score(score: float) -> Action:
    if score >= 80:
        return "strong_buy"
    if score >= 65:
        return "buy"
    if score >= 45:
        return "hold"
    if score >= 30:
        return "reduce"
    return "avoid"


def score_stock_signal(symbol: str, horizon: Horizon = "short") -> Dict[str, Any]:
    """
    High‑level helper used by the Advisor V2 endpoints.

    Returns:
    {
      "symbol": ...,
      "quote": {...},         # from get_stock_detail
      "ensemble": {...},      # from prediction_engine
      "technical_score": {...},
      "signal": {
        "action": "buy" | ...,
        "score": 0–100
      }
    }
    """
    quote = get_stock_detail(symbol)
    ensemble = ensemble_forecast(symbol, horizon=horizon)
    tech = _score_from_technicals(symbol)

    # Blend forecast and technical scores with equal weight
    forecast_score = _score_from_forecast(ensemble) if ensemble else 50.0
    tech_score = tech["score"]
    blended = (forecast_score + tech_score) / 2.0

    action = _action_from_score(blended)

    return {
        "symbol": (quote or {}).get("symbol", symbol),
        "quote": quote,
        "ensemble": ensemble,
        "technical_score": tech,
        "signal": {
            "action": action,
            "score": round(blended, 1),
        },
    }

