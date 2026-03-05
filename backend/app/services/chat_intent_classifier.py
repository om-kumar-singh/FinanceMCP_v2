"""
Structured intent + entity extraction for conversational /chat routing.

This is intentionally deterministic and explainable (rule-based scoring),
so it remains stable and doesn't introduce new dependencies or data sources.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.services.advisor_v5.query_parser import parse_query
from app.services.symbol_dictionary import COMMON_COMPANY_ALIASES
from app.services.stock_search_service import resolve_symbol


INTENTS: Tuple[str, ...] = (
    "stock_analysis",
    "technical_indicator",
    "comparison",
    "portfolio_analysis",
    "prediction",
    "advisor_recommendation",
    "market_regime",
    "volume_analysis",
    "market_news",
    "macro_economics",
    "investment_advice",
)

_TOKEN_STOPWORDS = {
    # Prevent accidental symbol resolution from common English words.
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
    "WHAT",
    "WHICH",
    "WHY",
    "HOW",
    "ABOUT",
    "TODAY",
    "NOW",
    "BUY",
    "SELL",
    "HOLD",
    "INVEST",
    "INVESTMENT",
    "PORTFOLIO",
    "COMPARE",
    "BETTER",
    "THAN",
    "PRICE",
    "STOCK",
    "STOCKS",
    "VOLUME",
    "UNUSUAL",
    "MARKET",
    "NEWS",
    "HEADLINES",
    "PREDICT",
    "PREDICTION",
    "FORECAST",
    "MODEL",
    "RSI",
    "MACD",
    "SMA",
    "EMA",
    "NSE",
    "BSE",
    "RBI",
    "GDP",
    "CPI",
}


FINANCE_KEYWORDS = {
    "stock",
    "share",
    "price",
    "pe",
    "p/e",
    "dividend",
    "yield",
    "market",
    "nifty",
    "sensex",
    "news",
    "macro",
    "inflation",
    "repo",
    "rbi",
    "gdp",
    "portfolio",
    "holdings",
    "allocation",
    "weights",
    "rsi",
    "macd",
    "moving average",
    "sma",
    "ema",
    "volume",
    "prediction",
    "forecast",
    "optimize",
    "diversify",
    "invest",
}


@dataclass
class ClassifiedQuery:
    intent: str
    confidence: float
    symbols: List[str]
    primary_symbol: Optional[str]
    indicator_type: Optional[str] = None  # rsi/macd/moving_averages/technical
    wants_amount_inr: Optional[float] = None
    debug: Dict[str, Any] = None


def _extract_symbol_aliases(text: str) -> List[str]:
    low = (text or "").lower()
    out: List[str] = []
    for k, sym in sorted(COMMON_COMPANY_ALIASES.items(), key=lambda kv: -len(kv[0])):
        if k in low:
            out.append(sym)
    return out


def _normalize_symbol_token(tok: str) -> Optional[str]:
    if not tok:
        return None
    t = str(tok).strip().upper()
    if not t:
        return None
    if t in _TOKEN_STOPWORDS:
        return None
    if t.startswith("^") or t.endswith(".NS") or t.endswith(".BO"):
        return t
    # Strict: only resolve if our resolver can map it; otherwise return None.
    return resolve_symbol(t)


def _extract_amount_inr(query: str) -> Optional[float]:
    """
    Extract INR amount from query.
    Handles: "₹1 lakh", "1 lakh", "100000", "1,00,000", "₹ 2.5 lakh", "₹10k".
    Returns amount in rupees.
    """
    q = (query or "").lower()
    if not q:
        return None

    # Normalize commas
    qn = q.replace(",", "")

    # lakh/crore forms
    m = re.search(r"(?:₹\s*)?(\d+(?:\.\d+)?)\s*(lakh|lac|crore|cr)\b", qn)
    if m:
        val = float(m.group(1))
        unit = m.group(2)
        if unit in {"lakh", "lac"}:
            return val * 100000.0
        if unit in {"crore", "cr"}:
            return val * 10000000.0

    # k / thousand
    m = re.search(r"(?:₹\s*)?(\d+(?:\.\d+)?)\s*k\b", qn)
    if m:
        return float(m.group(1)) * 1000.0

    # plain number (must be large enough to be investment amount)
    m = re.search(r"(?:₹\s*)?(\d{5,})\b", qn)
    if m:
        return float(m.group(1))

    return None


def extract_symbols(query: str, *, context: Optional[Dict[str, Any]] = None) -> List[str]:
    """
    Extract and normalize symbols from query text.
    Never substitutes random tickers: if a token can't be resolved, it is dropped.
    """
    ctx = context or {}
    q = (query or "").strip()
    if not q:
        return []

    parsed = parse_query(q, context=ctx)
    raw_syms = list(parsed.get("symbols") or [])
    raw_syms.extend(_extract_symbol_aliases(q))

    out: List[str] = []
    seen = set()
    for tok in raw_syms:
        sym = _normalize_symbol_token(tok)
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out


def _indicator_type(query: str) -> Optional[str]:
    q = (query or "").lower()
    if "rsi" in q:
        return "rsi"
    if "macd" in q:
        return "macd"
    if "moving average" in q or "moving-averages" in q or re.search(r"\bsma\b|\bema\b", q):
        return "moving_averages"
    if any(w in q for w in ("technical", "indicator", "technicals")):
        return "technical"
    return None


def has_finance_signal(query: str) -> bool:
    q = (query or "").lower()
    return any(k in q for k in FINANCE_KEYWORDS)


def classify_intent(query: str, *, context: Optional[Dict[str, Any]] = None) -> ClassifiedQuery:
    """
    Classify query into one of the supported intents with a confidence score.
    """
    ctx = context or {}
    q = (query or "").strip()
    ql = q.lower()

    syms = extract_symbols(q, context=ctx)
    primary = syms[0] if syms else (ctx.get("last_symbol") if isinstance(ctx.get("last_symbol"), str) else None)

    amount = _extract_amount_inr(q)
    ind = _indicator_type(q)

    # Feature flags
    f_compare = bool(re.search(r"\b(compare|vs|versus|better)\b", ql))
    f_portfolio = ("portfolio" in ql) or ("holdings" in ql) or ("positions" in ql) or bool(re.search(r"\d+\s*%.*\d+\s*%", ql, re.S))
    f_predict = bool(re.search(r"\b(predict|prediction|forecast|target price|price target|model)\b", ql))
    f_buy = bool(re.search(r"\b(should i buy|buy now|sell|hold|good investment|worth buying|recommend)\b", ql))
    f_invest_advice = bool(re.search(r"\b(which stocks|what stocks|pick stocks|choose stocks|suggest stocks|diversif)\b", ql)) and ("invest" in ql or amount is not None)
    f_news = "news" in ql or "headlines" in ql
    f_macro = bool(re.search(r"\b(inflation|repo|rbi|gdp|budget|rupee)\b", ql))
    f_market_ctx = bool(re.search(r"\b(market regime|regime|bullish|bearish|sector|sectors strongest|market outlook)\b", ql))
    f_volume = bool(re.search(r"\b(volume|unusual volume|volume spike|institutional|smart money|accumulation|distribution)\b", ql))
    f_stock_analysis = bool(re.search(r"\b(analy[sz]e|analysis|tell me about|fundamentals|valuation|pe ratio|dividend)\b", ql))

    # Scoring (0–1)
    candidates: List[Tuple[str, float]] = []
    if f_invest_advice:
        candidates.append(("investment_advice", 0.95))
    if ind:
        candidates.append(("technical_indicator", 0.92))
    if f_compare:
        candidates.append(("comparison", 0.9 if len(syms) >= 2 else 0.7))
    if f_portfolio:
        candidates.append(("portfolio_analysis", 0.9))
    if f_predict:
        candidates.append(("prediction", 0.88))
    if f_buy:
        candidates.append(("advisor_recommendation", 0.9 if primary else 0.65))
        candidates.append(("investment_advice", 0.8 if not primary else 0.6))
    if f_volume:
        candidates.append(("volume_analysis", 0.85 if primary else 0.7))
    if f_market_ctx:
        candidates.append(("market_regime", 0.82))
    if f_news:
        candidates.append(("market_news", 0.8))
    if f_macro:
        candidates.append(("macro_economics", 0.78))
    if f_stock_analysis:
        candidates.append(("stock_analysis", 0.75 if primary else 0.55))

    # If a symbol exists but nothing else matched, default to stock_analysis.
    if not candidates and primary:
        candidates.append(("stock_analysis", 0.55))

    if not candidates:
        return ClassifiedQuery(
            intent="unknown",
            confidence=0.0,
            symbols=syms,
            primary_symbol=primary if primary in syms else (syms[0] if syms else None),
            indicator_type=ind,
            wants_amount_inr=amount,
            debug={"features": {}},
        )

    # choose best; tie-break by preferred priority order
    priority = {name: i for i, name in enumerate(INTENTS)}
    candidates.sort(key=lambda x: (x[1], -priority.get(x[0], 999)), reverse=True)
    best_intent, best_conf = candidates[0]

    return ClassifiedQuery(
        intent=best_intent,
        confidence=float(best_conf),
        symbols=syms,
        primary_symbol=primary if primary else (syms[0] if syms else None),
        indicator_type=ind,
        wants_amount_inr=amount,
        debug={
            "candidates": candidates[:5],
            "symbols": syms,
            "amount_inr": amount,
            "indicator_type": ind,
        },
    )

