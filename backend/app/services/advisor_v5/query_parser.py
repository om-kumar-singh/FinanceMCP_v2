"""
Natural-language query parser for Advisor V5.

Converts free-form user questions into a structured intent with
symbols, portfolio flags, and analysis type hints.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def _extract_symbols(text: str) -> List[str]:
    """
    Very lightweight symbol extractor.
    Recognises patterns like RELIANCE, RELIANCE.NS, TCS, TCS.NS, etc.
    """
    tokens = re.findall(r"\b[A-Z]{2,10}(?:\.NS|\.BO)?\b", text.upper())
    # Deduplicate while preserving order
    seen = set()
    symbols: List[str] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            symbols.append(t)
    return symbols


def parse_query(query: str, *, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Parse user query into intent and entities.

    Returns:
    {
      "intent": "...",
      "symbols": [...],
      "primary_symbol": "...",
      "analysis_type": "...",
      "wants_portfolio": bool,
      "wants_market_outlook": bool,
      "wants_top_picks": bool,
      "raw": query,
      "context": context or {}
    }
    """
    ctx = context or {}
    q = (query or "").strip()
    q_lower = q.lower()

    symbols = _extract_symbols(q)
    primary_symbol: Optional[str] = symbols[0] if symbols else None

    # Fall back to previous symbol in context (for follow‑ups like "Is it better than TCS?")
    prev_symbol = ctx.get("last_symbol")

    # Intent classification
    intent = "general"
    analysis_type = "general"
    wants_portfolio = False
    wants_market_outlook = False
    wants_top_picks = False

    if any(w in q_lower for w in ("portfolio", "my holdings", "my stocks", "my positions")):
        wants_portfolio = True
        if any(w in q_lower for w in ("optimize", "optimise", "efficient frontier", "allocation", "weights")):
            intent = "portfolio_optimization"
            analysis_type = "portfolio_optimization"
        elif any(w in q_lower for w in ("risk", "var", "drawdown", "volatility")):
            intent = "portfolio_risk"
            analysis_type = "portfolio_risk"
        else:
            intent = "portfolio_overview"
            analysis_type = "portfolio_overview"
    elif any(w in q_lower for w in ("market regime", "market outlook", "macro view", "bullish", "bearish")):
        intent = "market_outlook"
        analysis_type = "market_regime"
        wants_market_outlook = True
    elif any(w in q_lower for w in ("top ai", "top picks", "best stocks", "what should i buy", "recommend stocks")):
        intent = "top_picks"
        analysis_type = "stock_screen"
        wants_top_picks = True
    elif any(w in q_lower for w in ("compare", "better than", "vs ", "versus")) and (primary_symbol or prev_symbol):
        intent = "stock_comparison"
        analysis_type = "stock_comparison"
    elif any(w in q_lower for w in ("buy", "sell", "hold", "should i", "is now a good time")):
        intent = "stock_recommendation"
        analysis_type = "stock_analysis"
    elif any(w in q_lower for w in ("momentum", "strong momentum", "trend", "breakout")):
        intent = "momentum_screen"
        analysis_type = "momentum_screen"
    elif any(w in q_lower for w in ("risk of", "risk in", "is it risky", "drawdown")) and (primary_symbol or prev_symbol):
        intent = "stock_risk"
        analysis_type = "stock_risk"
    else:
        intent = "general"
        analysis_type = "general"

    if not primary_symbol and prev_symbol and intent in {"stock_recommendation", "stock_risk", "stock_analysis"}:
        primary_symbol = prev_symbol

    return {
        "intent": intent,
        "analysis_type": analysis_type,
        "symbols": symbols,
        "primary_symbol": primary_symbol,
        "wants_portfolio": wants_portfolio,
        "wants_market_outlook": wants_market_outlook,
        "wants_top_picks": wants_top_picks,
        "raw": query,
        "context": ctx,
    }

