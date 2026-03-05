"""
Structured financial report generator for Advisor V5.

Builds concise, human-readable reports that can also be rendered in
markdown or plain text.
"""

from __future__ import annotations

from typing import Any, Dict, List


def build_stock_report(symbol: str, v3: Dict[str, Any], v4: Dict[str, Any]) -> str:
    """
    Stock Analysis Report from Advisor V3 + V4 outputs.
    """
    sym = symbol.replace(".NS", "").replace(".BO", "")
    rec = v3.get("recommendation")
    conf = v3.get("confidence")
    exp_ret = v3.get("expected_return")
    factors = v3.get("factor_scores") or {}

    strategy = v4.get("strategy") or {}
    smart = v4.get("smart_money") or {}

    lines: List[str] = []
    lines.append("Stock Analysis Report")
    lines.append("")
    lines.append(f"Symbol: {sym}")
    lines.append(f"Recommendation: {rec}")
    if exp_ret is not None:
        lines.append(f"Expected Return (short horizon): {round(float(exp_ret) * 100, 2)}%")
    if conf is not None:
        lines.append(f"Confidence: {round(float(conf) * 100, 1)}%")
    lines.append("")
    lines.append("Key Factors:")
    lines.append(f"- Prediction Score: {round(factors.get('prediction', 0.0) * 100, 1)}/100")
    lines.append(f"- Momentum Score: {round(factors.get('momentum', 0.0) * 100, 1)}/100")
    lines.append(f"- Sentiment Score: {round(factors.get('sentiment', 0.0) * 100, 1)}/100")
    lines.append(f"- Trend Score: {round(factors.get('trend', 0.0) * 100, 1)}/100")
    lines.append("")

    if strategy:
        lines.append("Strategy Signals:")
        lines.append(
            f"- Strategy Ensemble: {strategy.get('strategy_signal')} "
            f"(strength {round(strategy.get('strategy_strength', 0.0) * 100, 1)}/100)"
        )
    if smart:
        lines.append(
            f"- Smart Money Activity: {smart.get('institutional_activity')} "
            f"(confidence {round(smart.get('confidence', 0.0) * 100, 1)}%)"
        )

    return "\n".join(lines)


def build_portfolio_report(portfolio_block: Dict[str, Any], risk_summary: Dict[str, Any]) -> str:
    """
    Portfolio Risk / Optimization report.
    """
    opt = portfolio_block.get("optimizer") or {}
    risk = risk_summary or {}

    lines: List[str] = []
    lines.append("Portfolio Risk Report")
    lines.append("")
    lines.append(f"Diversification Score: {opt.get('diversification_score')}")
    lines.append(f"Optimized Expected Return (daily): {opt.get('expected_return')}")
    lines.append(f"Optimized Volatility (daily): {opt.get('volatility')}")
    lines.append("")
    lines.append("Risk Metrics:")
    metrics = risk.get("risk_metrics") or {}
    lines.append(f"- VaR 95%: {metrics.get('var_95')}")
    lines.append(f"- Expected Shortfall 95%: {metrics.get('expected_shortfall_95')}")
    lines.append(f"- Beta vs Market: {metrics.get('beta_vs_market')}")
    lines.append(f"- Volatility (daily): {metrics.get('volatility')}")
    lines.append(f"- Max Drawdown: {metrics.get('max_drawdown')}")
    lines.append(f"- Risk Score: {risk.get('risk_score')} ({risk.get('risk_category')})")

    return "\n".join(lines)


def build_market_outlook_report(regime: Dict[str, Any]) -> str:
    """
    Market Outlook report.
    """
    mr = regime.get("market_regime")
    ts = regime.get("trend_strength")
    vol = regime.get("volatility_level")

    lines: List[str] = []
    lines.append("Market Outlook Report")
    lines.append("")
    lines.append(f"Market Regime: {mr}")
    lines.append(f"Trend Strength: {ts}")
    lines.append(f"Volatility Level: {vol}")

    return "\n".join(lines)

