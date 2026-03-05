"""
Natural-language response generator for Advisor V5.

Converts structured analysis + reports + insights into a conversational
assistant-style answer.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_chat_response(
    query: str,
    parsed: Dict[str, Any],
    analysis: Dict[str, Any],
    *,
    stock_report: Optional[str] = None,
    portfolio_report: Optional[str] = None,
    market_report: Optional[str] = None,
    insights: Optional[List[str]] = None,
) -> str:
    """
    Assemble a concise, conversational answer.
    """
    intent = parsed.get("intent")
    symbol = analysis.get("symbol") or parsed.get("primary_symbol")
    sym_clean = (symbol or "").replace(".NS", "").replace(".BO", "")

    lines: List[str] = []

    if intent in {"stock_recommendation", "stock_analysis", "stock_risk"} and symbol:
        v3 = analysis.get("advisor_v3") or analysis.get("advisor_v4", {}).get("advisor_v3", {})
        rec = v3.get("recommendation")
        conf = v3.get("confidence")
        exp_ret = v3.get("expected_return")
        mr = v3.get("market_regime") or analysis.get("advisor_v4", {}).get("market_regime")

        opening = f"For {sym_clean}, my current view is **{rec}**"
        if conf is not None:
            opening += f" with confidence around {round(float(conf) * 100, 1)}%."
        else:
            opening += "."
        lines.append(opening)

        if exp_ret is not None:
            lines.append(
                f"Over the short-term horizon, the ensemble model expects roughly {round(float(exp_ret) * 100, 1)}% move."
            )
        if mr:
            lines.append(f"Broad market regime currently looks {mr}, which shapes how aggressive this view should be.")
    elif intent in {"portfolio_risk", "portfolio_overview", "portfolio_optimization"}:
        risk = analysis.get("portfolio_risk") or {}
        rs = risk.get("risk_score")
        cat = risk.get("risk_category")
        lines.append(
            f"Based on your portfolio, the overall risk score is {rs} which I classify as {cat} risk."
        )
    elif intent in {"market_outlook"}:
        regime = analysis.get("market_regime") or {}
        lines.append(
            f"The current market regime is {regime.get('market_regime')} with trend strength {regime.get('trend_strength')} and volatility in the {regime.get('volatility_level')} range."
        )
    else:
        # General fallback
        if symbol:
            lines.append(f"Here is my latest view on {sym_clean} based on current models and market data.")
        else:
            lines.append("Here is what I infer from current models and market data.")

    if insights:
        lines.append("")
        lines.append("Key Insights:")
        for ins in insights[:5]:
            lines.append(f"- {ins}")

    # Optionally append a compact stock/portfolio/market report if present
    if stock_report and intent in {"stock_recommendation", "stock_analysis", "stock_risk"}:
        lines.append("")
        lines.append(stock_report)
    if portfolio_report and intent in {"portfolio_risk", "portfolio_overview", "portfolio_optimization"}:
        lines.append("")
        lines.append(portfolio_report)
    if market_report and intent in {"market_outlook"}:
        lines.append("")
        lines.append(market_report)

    return "\n".join(lines)

