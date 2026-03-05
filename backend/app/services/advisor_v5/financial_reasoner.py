"""
Financial reasoning engine for Advisor V5.

Routes parsed user intents to underlying advisor engines:
- Advisor V3 (single-stock reasoning)
- Advisor V4 (quant layer)
- V4 portfolio optimizer and risk engine
- V4 regime detector and strategy engine
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.advisor_v3.reasoning_engine import analyse_symbol_v3
from app.services.advisor_v4.portfolio_optimizer import optimize_portfolio
from app.services.advisor_v4.quant_engine import quant_analyse
from app.services.advisor_v4.regime_detection import detect_market_regime
from app.services.advisor_v4.risk_engine import summarise_risk
from app.services.advisor_v4.strategy_engine import ensemble_strategy_signal


def reason_about_query(
    parsed: Dict[str, Any],
    *,
    portfolio: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    High-level orchestrator that decides which engines to call.

    Returns a dict with 'intent', 'analysis', and any supporting blocks.
    """
    intent = parsed.get("intent")
    symbol = parsed.get("primary_symbol")

    analysis: Dict[str, Any] = {"intent": intent}

    if intent in {"stock_recommendation", "stock_risk", "stock_analysis"} and symbol:
        v3 = analyse_symbol_v3(symbol, portfolio=portfolio)
        v4 = quant_analyse(symbol, portfolio=portfolio)
        analysis["symbol"] = symbol
        analysis["advisor_v3"] = v3
        analysis["advisor_v4"] = v4
    elif intent in {"stock_comparison"} and parsed.get("symbols"):
        # For now, call V3/V4 for first symbol and rely on existing /compare route for UI tooling.
        s1 = parsed["symbols"][0]
        v3 = analyse_symbol_v3(s1, portfolio=portfolio)
        v4 = quant_analyse(s1, portfolio=portfolio)
        analysis.update({"symbol": s1, "advisor_v3": v3, "advisor_v4": v4})
    elif intent in {"portfolio_risk", "portfolio_overview", "portfolio_optimization"} and portfolio:
        # Use Optimizer + Risk engine on the provided holdings
        symbols = sorted({p["symbol"] for p in portfolio})
        opt = optimize_portfolio(symbols)
        weights = opt.get("weights") or {}
        risk = summarise_risk(weights)
        regime = detect_market_regime("^NSEI")
        analysis.update(
            {
                "portfolio_optimizer": opt,
                "portfolio_risk": risk,
                "market_regime": regime,
            }
        )
    elif intent in {"market_outlook"}:
        regime = detect_market_regime("^NSEI")
        analysis["market_regime"] = regime
    elif intent in {"momentum_screen"} and symbol:
        # For symbol-focused momentum query, use V4 strategy engine plus V3.
        v3 = analyse_symbol_v3(symbol, portfolio=portfolio)
        strat = ensemble_strategy_signal(symbol)
        analysis.update({"symbol": symbol, "advisor_v3": v3, "strategy": strat})
    elif intent in {"top_picks"}:
        # No dedicated screener yet; use a placeholder that can be extended later.
        regime = detect_market_regime("^NSEI")
        analysis["market_regime"] = regime
        analysis["top_picks"] = []  # Reserved for future screening integration.
    else:
        # General / fallback: provide at least market regime and, if a symbol exists, V3.
        regime = detect_market_regime("^NSEI")
        analysis["market_regime"] = regime
        if symbol:
            v3 = analyse_symbol_v3(symbol, portfolio=portfolio)
            analysis["symbol"] = symbol
            analysis["advisor_v3"] = v3

    return analysis

