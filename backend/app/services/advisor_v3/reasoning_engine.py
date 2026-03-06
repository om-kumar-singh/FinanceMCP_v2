"""
Advisor V3 reasoning engine.

High‑level, ChatGPT‑style financial analyst that combines:
- ensemble prediction (Advisor V2)
- signal scoring (Advisor V2)
- portfolio risk (Advisor V2)
- market context (Advisor V3)
- simple news sentiment

This module does not call any new data sources; it reuses the existing
services built on yfinance and other APIs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.advisor_v2.portfolio_risk import analyse_portfolio_v2
from app.services.advisor_v2.signal_scoring import score_stock_signal
from app.services.advisor_v3.market_context import get_market_context
from app.services.news_service import get_market_news


def _sentiment_from_headlines(symbol: str, max_items: int = 10) -> Dict[str, Any]:
    """
    Lightweight sentiment approximation based on news headlines.
    """
    items = get_market_news(symbol) or []
    headlines = [str(x.get("title") or "") for x in items[:max_items]]
    if not headlines:
        return {
            "score": 0.5,
            "label": "neutral",
            "sample_headlines": [],
        }

    positive_keywords = [
        "rally",
        "beats estimates",
        "upgrade",
        "growth",
        "record",
        "surge",
        "strong",
        "profit",
    ]
    negative_keywords = [
        "plunge",
        "downgrade",
        "misses estimates",
        "fraud",
        "loss",
        "crash",
        "probe",
        "regulatory action",
    ]

    pos = 0
    neg = 0
    for title in headlines:
        low = title.lower()
        if any(k in low for k in positive_keywords):
            pos += 1
        if any(k in low for k in negative_keywords):
            neg += 1

    total = max(pos + neg, 1)
    raw = 0.5 + (pos - neg) / (2.0 * total)
    score = max(0.0, min(1.0, raw))

    if score >= 0.65:
        label = "positive"
    elif score <= 0.35:
        label = "negative"
    else:
        label = "neutral"

    return {
        "score": round(score, 3),
        "label": label,
        "sample_headlines": headlines[:5],
    }


def _volume_signal(quote: Optional[Dict[str, Any]], history: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Approximate volume signal using last‑bar vs average volumes.
    """
    if not history or not history.get("volumes"):
        return {"score": 0.5, "label": "neutral"}

    vols = history["volumes"]
    if len(vols) < 10:
        return {"score": 0.5, "label": "neutral"}

    last = float(vols[-1])
    avg = float(sum(vols[-20:]) / min(len(vols), 20))
    if avg <= 0:
        return {"score": 0.5, "label": "neutral"}

    ratio = last / avg
    if ratio > 1.6:
        score = 0.8
        label = "accumulation"
    elif ratio > 1.2:
        score = 0.65
        label = "above_average"
    elif ratio < 0.6:
        score = 0.35
        label = "drying_up"
    else:
        score = 0.5
        label = "neutral"

    return {"score": score, "label": label, "volume_ratio": round(ratio, 2)}


def _volatility_adjustment(expected_vol: Optional[float]) -> float:
    """
    Map expected volatility into a 0–1 adjustment where 1 is favourable.
    """
    if expected_vol is None:
        return 0.5
    v = float(abs(expected_vol))
    if v <= 0.01:
        return 0.9
    if v <= 0.02:
        return 0.75
    if v <= 0.035:
        return 0.55
    if v <= 0.05:
        return 0.4
    return 0.25


def compute_multi_factor_score(
    symbol: str,
    *,
    include_portfolio: bool = False,
    portfolio: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Core multi‑factor scoring logic for Advisor V3.

    Implements:
      stock_score = 0.30*prediction_strength
                  + 0.20*momentum_signal
                  + 0.15*sentiment_score
                  + 0.15*trend_strength
                  + 0.10*volume_signal
                  + 0.10*volatility_adjustment
    """
    # Base V2 signal/ensemble/technicals
    v2_payload = score_stock_signal(symbol, horizon="short")
    ensemble = v2_payload.get("ensemble") or {}
    tech = v2_payload.get("technical_score") or {}
    quote = v2_payload.get("quote") or {}

    # Market context & sentiment
    context = get_market_context(symbol)
    sentiment = _sentiment_from_headlines(symbol)

    # Optional portfolio context
    portfolio_block: Optional[Dict[str, Any]] = None
    if include_portfolio and portfolio:
        portfolio_block = analyse_portfolio_v2(portfolio)

    # Prediction strength: use expected_return + model confidence
    exp_ret = ensemble.get("expected_return")
    conf = (ensemble.get("confidence") or {}).get("score", 0.0)
    if exp_ret is None:
        prediction_strength = 0.5
    else:
        # +5% => ~0.8, 0% => 0.5, -5% => ~0.2
        prediction_strength = 0.5 + float(exp_ret) * 5.0
        prediction_strength = max(0.0, min(1.0, prediction_strength))
        # Tilt towards neutral if confidence is low
        prediction_strength = prediction_strength * conf + 0.5 * (1.0 - conf)

    # Momentum/trend from technicals
    momentum_signal = 0.5
    trend_strength = 0.5
    details = tech.get("details") or []
    for d in details:
        low = d.lower()
        if "rsi" in low and "oversold" in low:
            momentum_signal += 0.15
        if "rsi" in low and "overbought" in low:
            momentum_signal -= 0.15
        if "macd bullish" in low:
            momentum_signal += 0.12
            trend_strength += 0.12
        if "macd bearish" in low:
            momentum_signal -= 0.12
            trend_strength -= 0.12
        if "above 200" in low:
            trend_strength += 0.1
        if "below 200" in low:
            trend_strength -= 0.1
    momentum_signal = max(0.0, min(1.0, momentum_signal))
    trend_strength = max(0.0, min(1.0, trend_strength))

    # Adjust trend_strength by sector and market regime
    if context.get("market_regime") == "bullish":
        trend_strength = min(1.0, trend_strength + 0.1)
    elif context.get("market_regime") == "bearish":
        trend_strength = max(0.0, trend_strength - 0.1)

    if context.get("sector_strength_score") is not None:
        sec_score = float(context["sector_strength_score"])
        # +2% day change -> +0.1; -2% -> -0.1
        trend_strength += max(-0.1, min(0.1, sec_score / 20.0))
        trend_strength = max(0.0, min(1.0, trend_strength))

    # Sentiment
    sentiment_score = float(sentiment["score"])

    # Volume signal
    from app.services.stock_service import get_stock_history  # local import to avoid cycles

    history = get_stock_history(symbol, period="3mo")
    volume = _volume_signal(quote, history)
    volume_signal = float(volume["score"])

    # Volatility adjustment
    vol_adj = _volatility_adjustment(ensemble.get("expected_volatility"))

    # Weighted stock score
    stock_score = (
        0.30 * prediction_strength
        + 0.20 * momentum_signal
        + 0.15 * sentiment_score
        + 0.15 * trend_strength
        + 0.10 * volume_signal
        + 0.10 * vol_adj
    )
    stock_score = max(0.0, min(1.0, stock_score))

    # Map to BUY / SELL / HOLD
    if stock_score >= 0.7:
        rec = "BUY"
    elif stock_score <= 0.35:
        rec = "SELL"
    elif prediction_strength < 0.45 and sentiment_score < 0.45:
        rec = "REDUCE"
    else:
        rec = "HOLD"

    # Confidence level for the recommendation
    overall_conf = (prediction_strength + sentiment_score + trend_strength) / 3.0
    if overall_conf >= 0.75:
        conf_level = "High"
    elif overall_conf >= 0.5:
        conf_level = "Medium"
    else:
        conf_level = "Low"

    factor_scores = {
        "prediction": round(prediction_strength, 3),
        "momentum": round(momentum_signal, 3),
        "sentiment": round(sentiment_score, 3),
        "trend": round(trend_strength, 3),
        "volume": round(volume_signal, 3),
        "volatility": round(vol_adj, 3),
    }

    # Growth-style composite score that can be reused for ranking candidates:
    # 0.5 * expected_return + 0.3 * momentum_score + 0.2 * sentiment_score
    try:
        exp_ret = ensemble.get("expected_return")
        exp_ret_f = float(exp_ret) if exp_ret is not None else 0.0
    except Exception:
        exp_ret_f = 0.0
    growth_score = 0.5 * exp_ret_f + 0.3 * momentum_signal + 0.2 * sentiment_score
    factor_scores["growth_score"] = round(growth_score, 3)

    institutional_block: Dict[str, Any] = {
        "model_prediction_breakdown": ensemble.get("models") or {},
        "factor_scores": factor_scores,
        "risk_metrics": {},
        "signal_strength": round(stock_score, 3),
        "technical_indicators": tech.get("indicators"),
        "sentiment_analysis": sentiment,
        "market_context": context,
    }

    # Enrich risk metrics if portfolio context provided
    if portfolio_block and not portfolio_block.get("error"):
        risk = portfolio_block.get("risk_metrics") or {}
        institutional_block["risk_metrics"] = risk

    return {
        "symbol": v2_payload.get("symbol", symbol),
        "recommendation": rec,
        "score": round(stock_score, 3),
        "confidence_level": conf_level,
        "confidence_score": round(overall_conf, 3),
        "expected_return": ensemble.get("expected_return"),
        "v2_payload": v2_payload,
        "factor_scores": factor_scores,
        "market_context": context,
        "sentiment": sentiment,
        "volume_signal": volume,
        "portfolio_block": portfolio_block,
        "institutional": institutional_block,
    }


def generate_explanation(analysis: Dict[str, Any]) -> str:
    """
    Turn the analysis dict into a concise, analyst-style explanation.
    """
    symbol = str(analysis.get("symbol") or "").replace(".NS", "").replace(".BO", "")
    rec = analysis.get("recommendation", "HOLD")
    conf = analysis.get("confidence_score", 0.5)
    exp_ret = analysis.get("expected_return")
    ctx = analysis.get("market_context") or {}
    factors = analysis.get("factor_scores") or {}
    sentiment = analysis.get("sentiment") or {}

    parts: List[str] = []
    parts.append(
        f"My current view on {symbol} is **{rec}** with confidence around {round(conf * 100, 1)}%."
    )

    if exp_ret is not None:
        parts.append(
            f"The ensemble model expects roughly {round(float(exp_ret) * 100, 1)}% "
            f"move over the short-term horizon."
        )

    # Market and sector context
    mr = ctx.get("market_regime")
    if mr in {"bullish", "neutral", "bearish"}:
        parts.append(f"Broad market regime appears **{mr}** based on recent NIFTY behaviour.")

    sec_sent = ctx.get("sector_sentiment")
    if sec_sent:
        parts.append(f"Sector sentiment is {sec_sent.lower()} with average moves near the top constituents.")

    # Factors
    if factors:
        pred = factors.get("prediction")
        mom = factors.get("momentum")
        sent = factors.get("sentiment")
        if pred is not None:
            parts.append(f"Prediction factor stands at {round(pred * 100, 1)}/100, reflecting the strength of model signals.")
        if mom is not None:
            parts.append(f"Momentum factor is {round(mom * 100, 1)}/100, driven by RSI/MACD and moving-average structure.")
        if sent is not None:
            parts.append(f"News sentiment scores about {round(sent * 100, 1)}/100 based on recent headlines.")

    # Sentiment detail
    if sentiment.get("label") and sentiment.get("sample_headlines"):
        label = sentiment["label"]
        parts.append(
            f"Recent news flow is {label}, for example: \"{sentiment['sample_headlines'][0]}\"."
        )

    # Risk note
    vol_adj = factors.get("volatility")
    if vol_adj is not None and vol_adj < 0.5:
        parts.append(
            "Volatility is elevated relative to typical levels, so position sizing and stop‑loss discipline matter more here."
        )

    return " ".join(parts)


def analyse_symbol_v3(
    symbol: str,
    *,
    portfolio: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    High‑level entry point for Advisor V3 single‑symbol analysis.
    """
    include_portfolio = bool(portfolio)
    mf = compute_multi_factor_score(symbol, include_portfolio=include_portfolio, portfolio=portfolio)
    explanation = generate_explanation(mf)

    ctx = mf["market_context"]
    factors = mf["factor_scores"]

    # Map to risk level label based on volatility factor + market regime
    vol_factor = factors.get("volatility", 0.5)
    mr = ctx.get("market_regime")
    if vol_factor >= 0.75:
        risk_level = "Low"
    elif vol_factor >= 0.5:
        risk_level = "Medium"
    else:
        risk_level = "High"
    if mr == "bearish" and risk_level != "High":
        risk_level = "Medium-High"

    return {
        "symbol": mf["symbol"],
        "recommendation": mf["recommendation"],
        "confidence": mf["confidence_score"],
        "expected_return": mf["expected_return"],
        "market_regime": ctx.get("market_regime"),
        "factor_scores": factors,
        "risk_level": risk_level,
        "explanation": explanation,
        "institutional": mf["institutional"],
    }

