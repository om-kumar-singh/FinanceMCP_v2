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


# Priority order for intent detection (first match wins when multiple flags set)
INTENTS: Tuple[str, ...] = (
    "growth_comparison",
    "long_term_comparison",
    "comparison",
    "portfolio_analysis",
    "portfolio_rebalance",
    "technical_indicator",
    "prediction",
    "buy_decision",
    "advisor_recommendation",
    "momentum_scan",
    "breakout_scan",
    "mean_reversion_scan",
    "institutional_activity",
    "accumulation_scan",
    "sector_flow_scan",
    "volume_scan",
    "market_insights",
    "market_risk",
    "market_trends",
    "ai_buy_signals",
    "ai_sector_beneficiaries",
    "ai_picks",
    "market_regime",
    "stock_analysis",
    "market_news",
    "macro_query",
    "macro_economics",
    "macro_analysis",
    "cross_market_impact",
    "news_query",
    "volume_analysis",
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
    "stocks",
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
    "predicted",
    "forecast",
    "expected return",
    "expected price",
    "predicted price",
    "volatility",
    "optimize",
    "diversify",
    "invest",
    "analyze",
    "analyse",
    "compare",
    "regime",
    "buy",
    "sell",
    "hold",
    "recommend",
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
    Returns only resolved symbols (e.g. RELIANCE.NS, TCS.NS).
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


def get_raw_parser_symbols(query: str, *, context: Optional[Dict[str, Any]] = None) -> List[str]:
    """
    Return raw symbol-like tokens from the query (before resolution).
    Used to detect when the user mentioned a symbol that could not be resolved.
    """
    ctx = context or {}
    q = (query or "").strip()
    if not q:
        return []
    parsed = parse_query(q, context=ctx)
    return list(parsed.get("symbols") or [])


def _indicator_type(query: str) -> Optional[str]:
    q = (query or "").lower()
    # Natural-language RSI variants
    if "overbought" in q or "oversold" in q:
        return "rsi"
    # Use word boundaries to avoid false positives (e.g. "reversion" contains "rsi")
    if re.search(r"\brsi\b", q):
        return "rsi"
    if re.search(r"\bmacd\b", q):
        return "macd"
    if "moving average" in q or "moving-averages" in q or re.search(r"\bsma\b|\bema\b", q):
        return "moving_averages"
    if re.search(r"\bbollinger\b", q):
        return "bollinger"
    if any(w in q for w in ("technical", "indicator", "technicals")):
        return "technical"
    return None


def has_finance_signal(query: str) -> bool:
    q = (query or "").lower()
    return any(k in q for k in FINANCE_KEYWORDS)


HYPOTHETICAL_MACRO_PHRASES = (
    "why would",
    "why does",
    "why is",
    "what if",
    "if gold",
    "if oil",
    "if yields",
    "if bond",
    "if rupee",
    "if vix",
    "when oil",
    "when gold",
    "when yields",
    "when bond",
    "when rupee",
    "suppose ",
    "assuming ",
    "hypothetically",
    "in case ",
)


def is_hypothetical_macro_query(query: str) -> bool:
    """If True, route to macro analysis and NEVER to portfolio."""
    ql = (query or "").lower()
    return any(phrase in ql for phrase in HYPOTHETICAL_MACRO_PHRASES)


def classify_intent(query: str, *, context: Optional[Dict[str, Any]] = None) -> ClassifiedQuery:
    """
    Classify query into one of the supported intents with a confidence score.
    """
    ctx = context or {}
    q = (query or "").strip()
    ql = q.lower()

    syms_all = extract_symbols(q, context=ctx)
    # Strict symbol filtering: only keep symbols that are explicitly present in the raw query text.
    # This avoids adding extra names from dictionaries, fuzzy matching, or search suggestions.
    explicit_tokens = {t.upper() for t in re.findall(r"[A-Za-z]{2,10}", q)}

    def _is_explicit(sym: str) -> bool:
        base = re.sub(r"\.(NS|BO)$", "", sym or "", flags=re.IGNORECASE).upper()
        return base in explicit_tokens

    syms = [s for s in syms_all if _is_explicit(s)]
    primary = syms[0] if syms else (ctx.get("last_symbol") if isinstance(ctx.get("last_symbol"), str) else None)

    amount = _extract_amount_inr(q)
    ind = _indicator_type(q)

    # Feature flags
    f_compare = bool(re.search(r"\b(compare|vs|versus|better than|better)\b", ql))
    f_portfolio_raw = ("portfolio" in ql) or ("holdings" in ql) or ("positions" in ql) or bool(re.search(r"\d+\s*%.*\d+\s*%", ql, re.S))
    f_portfolio = f_portfolio_raw and not is_hypothetical_macro_query(q)
    f_predict = bool(
        re.search(
            r"\b(predict|predicted|prediction|forecast|target price|price target|model|expected return|expected price|predicted price|short term forecast|price prediction|price forecast)\b",
            ql,
        )
    )
    f_buy = bool(
        re.search(
            r"\b("
            r"should i buy|"
            r"should i invest|"
            r"buy now|"
            r"sell now|"
            r"hold|"
            r"good investment|"
            r"is it a good investment|"
            r"good stock to buy|"
            r"worth buying|"
            r"worth (buying|investing)|"
            r"buy recommendation|"
            r"is .+ a good (buy|investment)|"
            r"is .+ worth (buying|investing)"
            r")\b",
            ql,
        )
    )
    f_invest_advice = bool(re.search(r"\b(which stocks|what stocks|pick stocks|choose stocks|suggest stocks|diversif)\b", ql)) and ("invest" in ql or amount is not None)
    f_ai_picks = bool(
        re.search(
            r"\b(top stocks|best forecast|highest predicted growth|strong predictions|ai picks|best predicted stocks|stocks with best forecast|top ai picks|which stocks have (highest |strong )?(predicted growth|ai predictions)|show stocks with best)\b",
            ql,
        )
    )
    f_momentum_scan = bool(re.search(r"\b(momentum|trending|strong trend|strong stocks)\b", ql))
    f_breakout_scan = bool(re.search(r"\b(breakout|price breakout|technical breakout)\b", ql))
    f_mean_reversion_scan = bool(re.search(r"\b(mean reversion|oversold stocks|bounce candidates)\b", ql))
    f_institutional = bool(
        re.search(r"\b(institutional buying|institutional selling|institutions buying|institutions selling|institutional|smart money)\b", ql)
    )
    f_accumulation_scan = bool(re.search(r"\b(accumulation|distribution)\b", ql))
    f_volume_scan = bool(re.search(r"\b(unusual volume|volume spike|spike in volume)\b", ql))
    f_sector_flow = bool(re.search(r"\b(it stocks|banking stocks|energy stocks)\b", ql)) and (
        "institution" in ql or "smart money" in ql or "buy" in ql or "selling" in ql
    )
    f_market_insights = bool(re.search(r"\b(market insights|ai market insights|today's market outlook|todays market outlook|market summary)\b", ql))
    f_market_risk = bool(re.search(r"\b(market risk|risks today|risk factors|what risks should investors watch)\b", ql))
    f_market_trends = bool(re.search(r"\b(market trends|emerging trends|what trends are emerging|sector trends)\b", ql))
    f_growth_cmp = bool(
        re.search(
            r"(growth potential|future growth|best growth stock|strong growth|growth outlook|expected return)",
            ql,
        )
    ) and bool(re.search(r"\b(which|better|vs|versus|compare)\b", ql))
    f_ai_buy_signals = bool(
        re.search(r"\b(strong ai buy signals|ai buy signals|strong buy signals|ai buy)\b", ql)
    )
    f_ai_sector_beneficiaries = bool(re.search(r"\b(ai growth|ai stocks|benefit from ai)\b", ql))
    f_long_term = bool(re.search(r"\b(long term investment|long-term investment|long term growth|long-term growth)\b", ql))
    f_news = bool(re.search(r"\b(news|headlines|latest (market )?news)\b", ql))
    f_macro = bool(re.search(r"\b(inflation|repo|rbi|gdp|budget|rupee|interest rate|macro)\b", ql))
    f_macro_signals = bool(
        re.search(
            r"\b(macro signals?|cross[- ]market|cross[- ]?asset|bond yield|bond yields|10y|10-year|10 yr|us 10y|treasury yield|"
            r"crude oil|brent|wti|oil price|oil prices?|usd\/inr|usd inr|currency rate|fx rate|forex|"
            r"gold price|gold rally|gold\b|india vix|vix)\b",
            ql,
        )
    )
    # "What happens when X" / "why would X be a warning" / "impact of X on Y" — route to macro
    f_macro_what_happens = bool(
        re.search(
            r"\b(what happens (to \w+ )?when |what happens when |how does .+ affect |"
            r"why would .+ be a warning|why does .+ (affect|mean)|why is .+ (a warning|important)|"
            r"impact of .+ on |effect of .+ on )",
            ql,
        )
    ) and (f_macro_signals or f_macro)
    # Market regime is intentionally narrow and should not compete with symbol-heavy queries.
    f_market_ctx = bool(
        re.search(r"\b(market regime|market trend|volatility increasing)\b", ql),
    )
    f_volume = bool(re.search(r"\b(volume|unusual volume|volume spike|institutional|smart money|accumulation|distribution)\b", ql))
    f_stock_analysis = bool(re.search(r"\b(analy[sz]e|analysis|tell me about|fundamentals|valuation|pe ratio|dividend)\b", ql))

    # Educational macro-style questions: why / how / what does / what if about macro concepts
    # "why would", "why does", "why is" must NEVER route to portfolio prompt
    f_edu_macro = bool(
        (f_macro or f_macro_signals or f_macro_what_happens)
        and re.search(r"\b(why would|why does|why is|why |how |what does|what if|what would)\b", ql)
    )

    # Hard rule (narrowed): force comparison ONLY when user explicitly asks to compare
    # and there are no buy/recommend/worth style intent words.
    if len(syms) >= 2 and not f_portfolio and f_compare and not f_buy:
        return ClassifiedQuery(
            intent="comparison",
            confidence=0.99,
            symbols=syms,
            primary_symbol=primary if primary else syms[0],
            indicator_type=ind,
            wants_amount_inr=amount,
            debug={
                "forced_multi_symbol_comparison": True,
                "symbols": syms,
            },
        )

    # Strict priority routing for macro & educational queries BEFORE generic scoring:
    # 1) "What happens when X" / "why would X" / "impact of X on Y" — always macro
    # 2) If message contains explicit macro signal keywords and is not a buy/portfolio weights query,
    #    treat as cross-market impact.
    if (f_macro_signals or f_macro or f_macro_what_happens) and not f_portfolio and not f_buy:
        if f_edu_macro:
            return ClassifiedQuery(
                intent="macro_analysis",
                confidence=0.99,
                symbols=syms,
                primary_symbol=primary if primary else (syms[0] if syms else None),
                indicator_type=ind,
                wants_amount_inr=amount,
                debug={"forced_macro_intent": "macro_analysis"},
            )
        return ClassifiedQuery(
            intent="cross_market_impact",
            confidence=0.99,
            symbols=syms,
            primary_symbol=primary if primary else (syms[0] if syms else None),
            indicator_type=ind,
            wants_amount_inr=amount,
            debug={"forced_macro_intent": "cross_market_impact"},
        )

    # Scoring: use explicit priority order for remaining intents
    # 1. portfolio intents
    # 2. comparison intents
    # 3. buy decision
    # 4. technical indicator queries
    # 5. prediction / AI picks
    # 6. market regime / insights
    # 7. macro and other analysis
    candidates: List[Tuple[str, float]] = []

    # 1) Portfolio
    if f_portfolio:
        if "rebalance" in ql:
            candidates.append(("portfolio_rebalance", 0.97))
        else:
            candidates.append(("portfolio_analysis", 0.97))

    # 2) Comparison-style intents (growth_comparison and generic comparison, long-term comparison)
    if f_growth_cmp:
        candidates.append(("growth_comparison", 0.96))
    if f_compare:
        candidates.append(("comparison", 0.95))
    if f_long_term and len(syms) >= 2:
        candidates.append(("long_term_comparison", 0.95))

    # 3) Buy / investment advice
    if f_buy:
        candidates.append(("buy_decision", 0.94 if primary else 0.72))
        candidates.append(("advisor_recommendation", 0.93 if primary else 0.70))
        if not primary:
            candidates.append(("investment_advice", 0.6))
    if f_invest_advice:
        candidates.append(("investment_advice", 0.88))

    # 4) Technical indicator queries
    if ind:
        candidates.append(("technical_indicator", 0.92))
    if f_momentum_scan and ("stocks" in ql or "which" in ql or "show" in ql or "scan" in ql):
        candidates.append(("momentum_scan", 0.94))
    if f_breakout_scan and ("stocks" in ql or "which" in ql or "show" in ql or "scan" in ql):
        candidates.append(("breakout_scan", 0.94))
    if f_mean_reversion_scan and ("stocks" in ql or "which" in ql or "show" in ql or "scan" in ql or "opportunit" in ql):
        candidates.append(("mean_reversion_scan", 0.94))
    # 5) Prediction / AI picks
    if f_ai_picks:
        # ai_picks (screener/ranking) beats prediction when both match (e.g. "which stocks have highest predicted growth")
        candidates.append(("ai_picks", 0.91))
    elif f_predict:
        candidates.append(("prediction", 0.90))

    if f_ai_buy_signals:
        candidates.append(("ai_buy_signals", 0.90))
    if f_ai_sector_beneficiaries:
        candidates.append(("ai_sector_beneficiaries", 0.89))

    # 6) Market regime / insights (never when symbols are present)
    if f_market_ctx and not syms:
        candidates.append(("market_regime", 0.88))
    if f_market_insights:
        candidates.append(("market_insights", 0.87))
    if f_market_risk:
        candidates.append(("market_risk", 0.87))
    if f_market_trends:
        candidates.append(("market_trends", 0.87))
    if f_sector_flow:
        candidates.append(("sector_flow_scan", 0.86))
    # 7) Other analysis, news, macro, volume
    if f_stock_analysis:
        candidates.append(("stock_analysis", 0.84 if primary else 0.55))
    if f_news:
        candidates.append(("news_query", 0.80))
    if f_macro:
        candidates.append(("macro_query", 0.79))
    if f_macro_signals:
        # Treat explicit macro-signal questions as dedicated intents so they do not fall back to clarification.
        candidates.append(("cross_market_impact", 0.90))
        candidates.append(("macro_analysis", 0.88))
    if f_accumulation_scan and ("stocks" in ql or "which" in ql or "show" in ql or "scan" in ql or "pattern" in ql):
        candidates.append(("accumulation_scan", 0.78))
    if f_volume_scan and ("stocks" in ql or "which" in ql or "show" in ql or "scan" in ql or "today" in ql):
        candidates.append(("volume_scan", 0.78))
    if f_institutional and primary:
        candidates.append(("institutional_activity", 0.77))
    if f_volume and not (f_volume_scan or f_accumulation_scan or f_sector_flow or f_institutional):
        candidates.append(("volume_analysis", 0.76 if primary else 0.65))

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

