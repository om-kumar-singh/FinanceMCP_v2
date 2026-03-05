"""
Natural-language query parser for Advisor V5.

Converts free-form user questions into a structured intent with
symbols, portfolio flags, and analysis type hints.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.services.symbol_dictionary import COMMON_COMPANY_ALIASES, BARE_TOKEN_ALLOWLIST


def _extract_symbols(text: str) -> List[str]:
    """
    Symbol extractor with India-centric alias support.

    - Recognizes company names like "HDFC Bank" using a curated mapping
    - Recognizes yfinance tickers like RELIANCE.NS
    - Recognizes bare tickers like TCS, INFY (filters common stopwords)
    """
    raw = (text or "").strip()
    if not raw:
        return []

    lower = raw.lower()

    # 1) Company aliases (prefer longer phrases first)
    found: List[str] = []
    for k, sym in sorted(COMMON_COMPANY_ALIASES.items(), key=lambda kv: -len(kv[0])):
        if k in lower:
            found.append(sym)

    # 2) Fully-qualified tickers (most reliable)
    qualified = re.findall(r"\b[A-Z][A-Z0-9&\-]{1,15}\.(?:NS|BO)\b", raw.upper())
    found.extend(qualified)

    # 3) Bare tokens (avoid 2-letter common words like IS/AN/TO)
    # Bare-token stopwords to avoid accidental ticker resolution:
    # e.g. "Is TCS..." should not treat "IS" as a symbol.
    stop = {
        "I",
        "ME",
        "MY",
        "WE",
        "YOU",
        "US",
        "IT",
        "THIS",
        "THAT",
        "THESE",
        "THOSE",
        "IS",
        "AM",
        "ARE",
        "WAS",
        "WERE",
        "BE",
        "BEEN",
        "BEING",
        "HAVE",
        "HAS",
        "HAD",
        "DO",
        "DID",
        "DOES",
        "AN",
        "THE",
        "A",
        "TO",
        "OF",
        "IN",
        "ON",
        "FOR",
        "WITH",
        "WITHOUT",
        "AND",
        "OR",
        "VS",
        "VERSUS",
        "COMPARE",
        "BETTER",
        "THAN",
        "WHAT",
        "WHICH",
        "WHY",
        "HOW",
        "ABOUT",
        "TELL",
        "SHOW",
        "GIVE",
        "TODAY",
        "NOW",
        "BUY",
        "SELL",
        "HOLD",
        "INVEST",
        "INVESTMENT",
        "PORTFOLIO",
        "RISK",
        "ANALYZE",
        "ANALYSE",
        "ANALYSIS",
        "PREDICT",
        "PREDICTION",
        "FORECAST",
        "MODEL",
        "TARGET",
        "PRICE",
        "STOCK",
        "STOCKS",
        "VOLUME",
        "UNUSUAL",
        "MOMENTUM",
        "BULLISH",
        "BEARISH",
        "REGIME",
        "MARKET",
        "NEWS",
        "HEADLINES",
        "RSI",
        "MACD",
        "SMA",
        "EMA",
        "PE",
        "P/E",
        "NAV",
        "NSE",
        "BSE",
        "RBI",
        "GDP",
        "CPI",
    }
    for tok in re.findall(r"\b[A-Z][A-Z0-9&\-]{1,15}\b", raw.upper()):
        if tok in stop:
            continue
        if len(tok) >= 3 or tok in BARE_TOKEN_ALLOWLIST:
            found.append(tok)

    # Deduplicate while preserving order
    seen = set()
    out: List[str] = []
    for t in found:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


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

