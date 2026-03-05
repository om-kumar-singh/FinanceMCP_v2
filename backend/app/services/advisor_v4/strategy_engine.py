"""
Quantitative strategy engine for Advisor V4.

Implements:
- momentum strategy
- mean reversion strategy
- trend-following strategy
- volatility breakout strategy

and combines them into a strategy ensemble score.
"""

from __future__ import annotations

from typing import Any, Dict

from app.services.stock_service import (
    calculate_bollinger_bands,
    calculate_macd,
    calculate_moving_averages,
    calculate_rsi,
    get_stock_history,
)


def _momentum_signal(symbol: str) -> float:
    hist = get_stock_history(symbol, period="6mo")
    closes = (hist or {}).get("closes") or []
    if len(closes) < 40:
        return 0.5
    recent = closes[-40:]
    short = recent[-10:]
    long = recent
    short_ret = (short[-1] - short[0]) / short[0] if short[0] else 0.0
    long_ret = (long[-1] - long[0]) / long[0] if long[0] else 0.0
    edge = short_ret - long_ret
    score = 0.5 + edge / 0.1  # +/-10% -> +/-0.5
    return max(0.0, min(1.0, score))


def _mean_reversion_signal(symbol: str) -> float:
    ma = calculate_moving_averages(symbol)
    rsi = calculate_rsi(symbol)
    if not ma and not rsi:
        return 0.5
    score = 0.5
    if rsi:
        val = float(rsi.get("rsi", 50))
        if val < 30:
            score += 0.2
        elif val > 70:
            score -= 0.2
    if ma:
        price = float(ma.get("price", 0.0))
        sma20 = float(ma.get("sma20", price))
        if sma20:
            dev = (price - sma20) / sma20
            if dev < -0.05:
                score += 0.15
            elif dev > 0.05:
                score -= 0.15
    return max(0.0, min(1.0, score))


def _trend_following_signal(symbol: str) -> float:
    ma = calculate_moving_averages(symbol)
    macd = calculate_macd(symbol)
    if not ma and not macd:
        return 0.5
    score = 0.5
    if ma:
        if ma.get("signal_sma50") == "above":
            score += 0.15
        elif ma.get("signal_sma50") == "below":
            score -= 0.15
        if ma.get("signal_sma200") == "above":
            score += 0.15
        elif ma.get("signal_sma200") == "below":
            score -= 0.15
    if macd:
        if macd.get("trend") == "bullish":
            score += 0.1
        elif macd.get("trend") == "bearish":
            score -= 0.1
    return max(0.0, min(1.0, score))


def _volatility_breakout_signal(symbol: str) -> float:
    bb = calculate_bollinger_bands(symbol)
    hist = get_stock_history(symbol, period="3mo")
    closes = (hist or {}).get("closes") or []
    if not bb or len(closes) < 20:
        return 0.5

    price = float(closes[-1])
    upper = float(bb.get("upper", price))
    lower = float(bb.get("lower", price))
    width = (upper - lower) / price if price else 0.0

    # Breakout when price near band extremes and bands relatively wide
    sig = bb.get("signal")
    score = 0.5
    if width > 0.08 and sig == "overbought":
        score -= 0.2
    elif width > 0.08 and sig == "oversold":
        score += 0.2
    elif width > 0.05:
        score += 0.05
    return max(0.0, min(1.0, score))


def ensemble_strategy_signal(symbol: str) -> Dict[str, Any]:
    """
    Combine strategy-level signals into a final strategy recommendation.

    strategy_score =
        0.30 * momentum_signal
      + 0.30 * trend_signal
      + 0.20 * mean_reversion_signal
      + 0.20 * volatility_breakout_signal
    """
    momentum = _momentum_signal(symbol)
    mean_rev = _mean_reversion_signal(symbol)
    trend = _trend_following_signal(symbol)
    vol_breakout = _volatility_breakout_signal(symbol)

    strategy_score = (
        0.30 * momentum
        + 0.30 * trend
        + 0.20 * mean_rev
        + 0.20 * vol_breakout
    )
    strategy_score = max(0.0, min(1.0, strategy_score))

    if strategy_score >= 0.7:
        signal = "BUY"
    elif strategy_score <= 0.3:
        signal = "SELL"
    elif strategy_score >= 0.55:
        signal = "OVERWEIGHT"
    elif strategy_score <= 0.45:
        signal = "UNDERWEIGHT"
    else:
        signal = "HOLD"

    return {
        "strategy_signal": signal,
        "strategy_strength": round(strategy_score, 3),
        "strategy_scores": {
            "momentum": round(momentum, 3),
            "mean_reversion": round(mean_rev, 3),
            "trend_following": round(trend, 3),
            "volatility_breakout": round(vol_breakout, 3),
        },
    }

