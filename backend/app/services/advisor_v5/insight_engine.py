"""
AI Insight Engine for Advisor V5.

Generates short, dashboard-friendly insights from:
- market regime
- V3 factor scores
- V4 strategy and smart-money signals
- portfolio risk / diversification
"""

from __future__ import annotations

from typing import Any, Dict, List


def generate_insights(analysis: Dict[str, Any]) -> List[str]:
    """
    Turn the merged analysis dict into a list of high-level insights.
    """
    insights: List[str] = []

    regime = analysis.get("market_regime") or analysis.get("advisor_v4", {}).get("market_regime")
    if isinstance(regime, dict):
        mr = regime.get("market_regime")
    else:
        mr = regime

    if mr == "bull_market":
        insights.append("Broad market regime appears bullish, which typically supports trend-following and momentum strategies.")
    elif mr == "bear_market":
        insights.append("Market is in a bearish regime; defensive positioning and risk control are more important.")
    elif mr == "sideways_market":
        insights.append("Market appears range-bound; mean-reversion and income strategies may be more effective than pure momentum.")

    v3 = analysis.get("advisor_v3") or analysis.get("advisor_v4", {}).get("advisor_v3")
    if v3:
        f = v3.get("factor_scores") or {}
        if f.get("momentum", 0) > 0.7:
            insights.append("Momentum indicators are strong for the symbol you asked about.")
        if f.get("sentiment", 0) > 0.7:
            insights.append("News sentiment is broadly positive, supporting a bullish thesis.")
        if f.get("volatility", 0.5) < 0.4:
            insights.append("Volatility is elevated; consider careful position sizing and staggered entries.")

    strat = analysis.get("strategy") or analysis.get("advisor_v4", {}).get("strategy")
    if strat:
        ss = strat.get("strategy_strength", 0.5)
        sig = strat.get("strategy_signal")
        if ss >= 0.7 and sig in {"BUY", "OVERWEIGHT"}:
            insights.append("The multi-strategy ensemble shows a strong positive bias (momentum + trend + breakout).")
        if ss <= 0.3 and sig in {"SELL", "UNDERWEIGHT"}:
            insights.append("Quant strategies collectively lean defensive or negative on this name.")

    smart = analysis.get("smart_money") or analysis.get("advisor_v4", {}).get("smart_money")
    if smart:
        ia = smart.get("institutional_activity")
        conf = smart.get("confidence", 0.0)
        if ia == "institutional_buying" and conf >= 0.6:
            insights.append("Volume and price action indicate possible institutional accumulation.")
        if ia == "distribution" and conf >= 0.6:
            insights.append("Patterns suggest institutional distribution, which can precede weakness.")

    # Portfolio-level insights if available
    portfolio_block = analysis.get("portfolio") or analysis.get("advisor_v4", {}).get("portfolio")
    if portfolio_block:
        opt = portfolio_block.get("optimizer") or {}
        div = opt.get("diversification_score")
        if div is not None:
            if div < 40:
                insights.append("Your portfolio appears concentrated; diversification could reduce idiosyncratic risk.")
            elif div > 70:
                insights.append("Your portfolio diversification score is strong, helping to smooth volatility.")

    return insights

