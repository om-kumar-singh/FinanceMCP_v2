"""
Advisor V4 quant integration engine.

Combines:
- Advisor V3 reasoning engine
- V4 market regime detector
- V4 strategy engine
- V4 smart money tracker
- V4 portfolio optimizer
- V4 risk engine

to produce an institutional-grade quant analysis object.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.advisor_v3.reasoning_engine import analyse_symbol_v3
from app.services.advisor_v4.portfolio_optimizer import optimize_portfolio
from app.services.advisor_v4.regime_detection import detect_market_regime
from app.services.advisor_v4.risk_engine import summarise_risk
from app.services.advisor_v4.smart_money_tracker import detect_smart_money
from app.services.advisor_v4.strategy_engine import ensemble_strategy_signal


def quant_analyse(
    symbol: str,
    portfolio: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    High-level quant analysis entry point for Advisor V4.
    """
    v3 = analyse_symbol_v3(symbol, portfolio=portfolio)
    regime = detect_market_regime("^NSEI")
    strat = ensemble_strategy_signal(symbol)
    smart = detect_smart_money(symbol)

    weights: Dict[str, float] = {}
    if portfolio:
        # Build naive weights from current portfolio by market value proxy (quantity * last price ~ approximated).
        # For optimization, use only symbols; risk engine will operate on optimized weights.
        symbols = sorted({p["symbol"] for p in portfolio})
        opt = optimize_portfolio(symbols)
        weights = opt.get("weights") or {}
        risk_summary = summarise_risk(weights)
        portfolio_block = {
            "optimizer": opt,
            "risk": risk_summary,
        }
    else:
        portfolio_block = None
        risk_summary = {
            "risk_score": None,
            "risk_category": None,
            "risk_metrics": {},
        }

    # Combine confidences from V3, strategy ensemble, and smart money
    v3_conf = float(v3.get("confidence") or 0.5)
    strat_strength = float(strat.get("strategy_strength") or 0.5)
    smart_conf = float(smart.get("confidence") or 0.5)

    combined_conf = (v3_conf + strat_strength + smart_conf) / 3.0

    # Portfolio impact heuristic
    if portfolio_block and portfolio_block.get("optimizer", {}).get("diversification_score") is not None:
        div_score = float(portfolio_block["optimizer"]["diversification_score"])
        if div_score >= 70:
            portfolio_impact = "improves diversification"
        elif div_score >= 40:
            portfolio_impact = "neutral for diversification"
        else:
            portfolio_impact = "may increase concentration risk"
    else:
        portfolio_impact = "insufficient data"

    return {
        "symbol": v3.get("symbol") or symbol,
        "market_regime": regime.get("market_regime"),
        "trend_strength": regime.get("trend_strength"),
        "volatility_level": regime.get("volatility_level"),
        "advisor_v3": v3,
        "strategy": strat,
        "smart_money": smart,
        "portfolio": portfolio_block,
        "risk": risk_summary,
        "combined_confidence": round(combined_conf, 3),
        "portfolio_impact": portfolio_impact,
    }

