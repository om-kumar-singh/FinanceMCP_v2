"""
Conversational advisor router for /chat.

Design goals:
- Keep existing frontend response shapes intact (source/result fields used by UI).
- Use Advisor V5 parser/reasoner for flexible intent detection.
- Add best-effort conversation memory (last_symbol).
- Add async timeout wrappers around blocking calls.
- Never raise to callers.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import anyio

from app.services.chat_intent_classifier import classify_intent, get_raw_parser_symbols, has_finance_signal
from app.services.mock_data import sample_mock_news
from app.services.news_service import get_market_news
from app.services.stock_search_service import resolve_symbol
from app.services.advisor_v5.response_generator import (
    _SOURCES_WITHOUT_FRONTEND_HANDLER,
    build_chat_response,
    format_advisor_output,
)

logger = logging.getLogger(__name__)


def _chat_response(payload: Dict[str, Any], updates: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Ensure chat always returns formatted text, never raw JSON."""
    if payload.get("result") is not None:
        try:
            # Global formatter: always convert advisor output into readable text.
            payload["message"] = build_chat_response(payload)
        except Exception:
            # Last-resort fallback: stringify bare result.
            payload["message"] = format_advisor_output(payload.get("result"))
        # For sources without frontend handlers, omit result so the frontend uses message
        # instead of falling through to "Here is what I found for X: {JSON}"
        if payload.get("source") in _SOURCES_WITHOUT_FRONTEND_HANDLER:
            payload["result"] = None
    return (payload, updates)

# Horizon display labels for forecasts
HORIZON_LABELS = {"intraday": "1-day", "short": "5-day", "medium": "20-day"}


def _horizon_label(horizon: str) -> str:
    return HORIZON_LABELS.get((horizon or "short").lower(), "5-day")


def _volatility_to_risk_level(vol: Optional[float]) -> str:
    """Convert expected volatility (fraction) to risk level: <0.03 Low, 0.03–0.06 Medium, >0.06 High."""
    if vol is None:
        return "N/A"
    try:
        v = float(vol)
        if v < 0.03:
            return "Low"
        if v <= 0.06:
            return "Medium"
        return "High"
    except Exception:
        return "N/A"


def _format_prediction_message(
    symbol: str,
    current_price: Optional[float],
    predicted_price: Optional[float],
    expected_return: Optional[float],
    horizon: str,
    confidence_label: Optional[str],
    risk_level: str,
    interpretation: str,
    risk_factors: str,
    conclusion: str,
) -> str:
    sym = (symbol or "").replace(".NS", "").replace(".BO", "")
    hl = _horizon_label(horizon)
    lines = [f"Prediction Summary – {sym}", ""]
    if current_price is not None:
        lines.append(f"Current Price: ₹{current_price:,.2f}")
    if predicted_price is not None:
        lines.append(f"Predicted Price ({hl} forecast): ₹{predicted_price:,.2f}")
    if expected_return is not None:
        pct = float(expected_return) * 100
        sign = "+" if pct >= 0 else ""
        lines.append(f"Expected Return ({hl} forecast): {sign}{pct:.2f}%")
    lines.append(f"Risk Level: {risk_level}")
    if confidence_label:
        lines.append(f"Confidence: {confidence_label}")
    lines.extend(["", "Interpretation:", interpretation, "", "Risk Factors:", risk_factors, "", "Conclusion:", conclusion])
    return "\n".join(lines)


def _format_ai_picks_message(ranked: List[Dict[str, Any]], horizon: str) -> str:
    hl = _horizon_label(horizon)
    lines = [f"Top AI Picks ({hl} forecast)", ""]
    for i, row in enumerate(ranked, 1):
        sym = (row.get("symbol") or "").replace(".NS", "").replace(".BO", "")
        er = row.get("expected_return")
        if er is not None:
            pct = float(er) * 100
            if abs(pct) < 0.2:
                pct_str = "~0%"
            else:
                pct_str = f"+{pct:.1f}%" if pct >= 0 else f"{pct:.1f}%"
        else:
            pct_str = "N/A"
        lines.append(f"{i}. {sym} → {pct_str}")
    return "\n".join(lines)


def _format_advisor_score_message(
    symbol: str,
    score_components: Dict[str, Any],
    final_score: int,
    recommendation: str,
    interpretation: str,
    risk_factors: str,
    conclusion: str,
) -> str:
    sym = (symbol or "").replace(".NS", "").replace(".BO", "")
    lines = [f"Advisor Recommendation – {sym}", "", "Score Breakdown"]
    comp = score_components or {}
    for key, val in comp.items():
        if isinstance(val, (int, float)):
            lines.append(f"{key.replace('_', ' ').title()}: {int(round(val * 100))}")
        else:
            lines.append(f"{key.replace('_', ' ').title()}: {val}")
    lines.extend(["", f"Final Score: {final_score} / 100", f"Recommendation: {recommendation}", "", "Interpretation:", interpretation, "", "Risk Factors:", risk_factors, "", "Conclusion:", conclusion])
    return "\n".join(lines)


def _format_comparison_message(comp: Dict[str, Any]) -> str:
    n1 = comp.get("name1", "")
    n2 = comp.get("name2", "")
    p1 = comp.get("price1")
    p2 = comp.get("price2")
    pe1 = comp.get("pe1")
    pe2 = comp.get("pe2")
    div1 = comp.get("dividendYield1") or 0
    div2 = comp.get("dividendYield2") or 0
    rec = comp.get("recommendation") or {}
    pref = rec.get("preferred")
    reason = rec.get("reason")
    lines = [f"Comparison: {n1} vs {n2}", ""]
    lines.append("Metrics:")
    if p1 is not None:
        lines.append(f"  {n1} – Price: ₹{p1:,.2f}, P/E: {pe1 if pe1 is not None else 'N/A'}, Dividend Yield: {div1}%")
    if p2 is not None:
        lines.append(f"  {n2} – Price: ₹{p2:,.2f}, P/E: {pe2 if pe2 is not None else 'N/A'}, Dividend Yield: {div2}%")
    interp = comp.get("interpretation") or []
    if interp:
        lines.extend(["", "Interpretation:"] + [f"  • {x}" for x in interp])
    if pref:
        lines.extend(["", "Conclusion:", f"  Preferred on metrics: {pref}. {reason or ''}"])
    return "\n".join(lines)


def _format_market_regime_message(regime: Dict[str, Any], interpretation: str, risk_factors: str, conclusion: str) -> str:
    lines = ["Market Regime Overview", ""]
    mr = regime.get("market_regime", "N/A")
    lines.append(f"Regime: {mr.replace('_', ' ').title()}")
    lines.extend(["", "Interpretation:", interpretation, "", "Risk Factors:", risk_factors, "", "Conclusion:", conclusion])
    return "\n".join(lines)


def _format_stock_analysis_message(detail: Dict[str, Any], interpretation: str, risk_factors: str) -> str:
    name = str(detail.get("symbol", "")).replace(".NS", "").replace(".BO", "")
    price = detail.get("price")
    pe = detail.get("pe")
    div = detail.get("dividendYield", 0) or 0
    sector = detail.get("sector", "N/A")
    lines = [f"Stock Analysis: {name}", ""]
    if price is not None:
        lines.append(f"Price: ₹{price:,.2f}")
    lines.append(f"P/E: {pe if pe is not None else 'N/A'}, Dividend Yield: {div}%, Sector: {sector}")
    lines.extend(["", "Interpretation:", interpretation, "", "Risk Factors:", risk_factors])
    return "\n".join(lines)


def _format_technical_message(symbol: str, result: Dict[str, Any], indicator_name: str) -> str:
    """Build readable message for RSI/MACD/moving_averages/technical_analysis result."""
    sym = (symbol or "").replace(".NS", "").replace(".BO", "")
    if result.get("error"):
        return f"{indicator_name} – {sym}: {result.get('error', 'No data')}"
    lines = [f"{indicator_name} – {sym}", ""]
    if result.get("rsi") is not None:
        lines.append(f"RSI: {result['rsi']} → {result.get('signal', 'N/A')}")
    if result.get("trend"):
        lines.append(f"MACD trend: {result['trend']}")
    if result.get("final_interpretation"):
        lines.append(result["final_interpretation"])
    if result.get("sma20") is not None:
        price = result.get("price") or result.get("current_price")
        price_str = f"₹{price:,.2f}" if isinstance(price, (int, float)) else "N/A"
        lines.append(f"Price: {price_str} | SMA20: {result['sma20']} | SMA50: {result.get('sma50')} | SMA200: {result.get('sma200')}")
        lines.append(f"Signal SMA200: {result.get('signal_sma200', 'N/A')}")
    if result.get("interpretation"):
        interp = result["interpretation"]
        if isinstance(interp, list):
            lines.extend(interp)
        else:
            lines.append(interp)
    return "\n".join(lines)


async def _run_sync_with_timeout(func, *args, timeout_s: float = 10.0, **kwargs):
    """
    Run a blocking function in a worker thread with a hard timeout.
    Returns None on timeout or error (errors are logged).
    """
    try:
        with anyio.fail_after(timeout_s):
            return await anyio.to_thread.run_sync(lambda: func(*args, **kwargs))
    except TimeoutError:
        logger.warning("Timeout calling %s", getattr(func, "__name__", "callable"))
        return None
    except Exception:
        logger.error("Error calling %s", getattr(func, "__name__", "callable"), exc_info=True)
        return None


def _normalize_symbol_maybe(s: str | None) -> Optional[str]:
    if not s:
        return None
    ss = str(s).strip().upper()
    if not ss:
        return None
    if ss.endswith(".NS") or ss.endswith(".BO") or ss.startswith("^"):
        return ss
    return resolve_symbol(ss) or None


def _extract_portfolio_allocations(query: str) -> List[Dict[str, Any]]:
    """
    Parse simple portfolio input patterns:
      "Reliance 40%"
      "TCS 30%"
      "HDFC Bank 30%"
    """
    q = (query or "").strip()
    if not q:
        return []

    # Match "name 40%" or "name: 40%"
    matches = re.findall(r"([A-Za-z&\.\s]{2,40})[:\-\s]+(\d{1,3}(?:\.\d+)?)\s*%", q)
    allocs: List[Dict[str, Any]] = []
    for name, pct in matches:
        try:
            w = float(pct)
        except Exception:
            continue
        if w <= 0:
            continue
        sym = resolve_symbol(name.strip()) or resolve_symbol(name.strip().upper())
        if not sym:
            # Try stripping common words
            sym = resolve_symbol(name.replace("bank", "").strip().upper())
        if not sym:
            continue
        allocs.append({"symbol": sym, "weight_percent": w})

    # Deduplicate by symbol (keep max weight if repeated)
    by_sym: Dict[str, float] = {}
    for a in allocs:
        s = a["symbol"]
        w = float(a["weight_percent"])
        by_sym[s] = max(by_sym.get(s, 0.0), w)
    return [{"symbol": s, "weight_percent": round(w, 2)} for s, w in by_sym.items()]


async def _comparison_result(symbols: List[str]) -> Optional[Dict[str, Any]]:
    if len(symbols) < 2:
        return None
    from app.services.stock_service import get_stock_detail

    s1 = _normalize_symbol_maybe(symbols[0])
    s2 = _normalize_symbol_maybe(symbols[1])
    if not s1 or not s2:
        return None

    d1 = await _run_sync_with_timeout(get_stock_detail, s1, timeout_s=10.0)
    d2 = await _run_sync_with_timeout(get_stock_detail, s2, timeout_s=10.0)
    if not isinstance(d1, dict) or not isinstance(d2, dict):
        return None
    if d1.get("error") or d2.get("error"):
        return None

    name1 = str(d1.get("symbol") or s1).replace(".NS", "").replace(".BO", "")
    name2 = str(d2.get("symbol") or s2).replace(".NS", "").replace(".BO", "")

    pe1 = d1.get("pe")
    pe2 = d2.get("pe")
    div1 = d1.get("dividendYield", 0) or 0
    div2 = d2.get("dividendYield", 0) or 0

    interpretation: List[str] = []
    if pe1 is not None and pe2 is not None:
        if pe1 < pe2:
            interpretation.append(f"{name1} has a lower PE ({pe1}) than {name2} ({pe2}), suggesting relatively cheaper valuation.")
        elif pe2 < pe1:
            interpretation.append(f"{name2} has a lower PE ({pe2}) than {name1} ({pe1}), suggesting relatively cheaper valuation.")
        else:
            interpretation.append("Both stocks trade at similar P/E multiples.")
    if div1 or div2:
        if div1 > div2:
            interpretation.append(f"{name1} has higher dividend yield ({div1}%) than {name2} ({div2}%).")
        elif div2 > div1:
            interpretation.append(f"{name2} has higher dividend yield ({div2}%) than {name1} ({div1}%).")

    # Simple preference heuristic (non-destructive): valuation + yield tie-break.
    preferred = None
    reason = None
    try:
        score1 = 0.0
        score2 = 0.0
        if pe1 is not None and pe2 is not None and pe1 != pe2:
            score1 += 1.0 if pe1 < pe2 else 0.0
            score2 += 1.0 if pe2 < pe1 else 0.0
        if float(div1) != float(div2):
            score1 += 0.5 if float(div1) > float(div2) else 0.0
            score2 += 0.5 if float(div2) > float(div1) else 0.0
        if score1 > score2:
            preferred = name1
            reason = "Lower valuation and/or higher yield on the compared metrics."
        elif score2 > score1:
            preferred = name2
            reason = "Lower valuation and/or higher yield on the compared metrics."
    except Exception:
        preferred = None

    return {
        "name1": name1,
        "name2": name2,
        "symbol1": d1.get("symbol") or s1,
        "symbol2": d2.get("symbol") or s2,
        "price1": d1.get("price"),
        "price2": d2.get("price"),
        "pe1": pe1,
        "pe2": pe2,
        "dividendYield1": div1,
        "dividendYield2": div2,
        "sector1": d1.get("sector"),
        "sector2": d2.get("sector"),
        "marketCap1": d1.get("marketCap"),
        "marketCap2": d2.get("marketCap"),
        "interpretation": interpretation,
        "recommendation": {"preferred": preferred, "reason": reason} if preferred else {"preferred": None, "reason": None},
    }


async def _multi_comparison_result(symbols: List[str]) -> Optional[Dict[str, Any]]:
    """
    Multi-stock comparison helper.

    For each symbol, fetches price, PE, dividend yield, sector, and market cap
    using existing stock_service functions and computes simple leaders:
    - lowest PE
    - highest dividend yield
    - largest market cap
    """
    from app.services.stock_service import get_stock_detail

    if len(symbols) < 2:
        return None

    rows: List[Dict[str, Any]] = []
    for raw in symbols:
        sym = _normalize_symbol_maybe(raw)
        if not sym:
            continue
        try:
            detail = await _run_sync_with_timeout(get_stock_detail, sym, timeout_s=10.0)
        except Exception:
            # Skip symbols that fail to fetch instead of crashing the comparison engine
            continue
        if not isinstance(detail, dict) or detail.get("error"):
            continue
        name = str(detail.get("symbol") or sym).replace(".NS", "").replace(".BO", "")
        pe = detail.get("pe")
        dy = detail.get("dividendYield", 0) or 0
        sector = detail.get("sector")
        price = detail.get("price")
        mc = detail.get("marketCap")
        rows.append(
            {
                "symbol": detail.get("symbol") or sym,
                "name": name,
                "price": price,
                "pe": pe,
                "dividendYield": dy,
                "sector": sector,
                "marketCap": mc,
            }
        )

    # Caller is responsible for enforcing minimum valid rows; keep rows even if < 2 for better messaging.

    def _float_or_none(x: Any) -> Optional[float]:
        try:
            return float(x)
        except Exception:
            return None

    def _parse_market_cap(x: Any) -> Optional[float]:
        """
        Convert market cap strings like \"9.3L Cr\" into a numeric value for comparison.
        The exact scale is less important than consistent ordering.
        """
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip().replace(",", "").lower()
        if not s:
            return None
        num_str = ""
        for ch in s:
            if ch.isdigit() or ch in {".", "-"}:
                num_str += ch
            elif num_str:
                break
        try:
            base = float(num_str)
        except Exception:
            return None
        factor = 1.0
        if "l" in s and "cr" in s:
            factor = 1e5  # lakh crore
        elif "cr" in s:
            factor = 1e2  # crore
        elif "l" in s:
            factor = 1e3  # lakh
        elif "t" in s:
            factor = 1e12  # trillion style
        return base * factor

    # Leaders and interpretation are computed defensively; any failure should not crash the advisor.
    interpretation: List[str] = []
    valuation_leader: Optional[Dict[str, Any]] = None
    income_leader: Optional[Dict[str, Any]] = None
    size_leader: Optional[Dict[str, Any]] = None
    growth_candidate: Optional[Dict[str, Any]] = None
    conclusion_lines: List[str] = []

    try:
        # Prepare numeric fields
        for r in rows:
            r["peNumeric"] = _float_or_none(r.get("pe"))
            r["dividendYieldNumeric"] = _float_or_none(r.get("dividendYield"))
            mc_num = _parse_market_cap(r.get("marketCap"))
            # If parsing fails, treat as 0 to keep comparisons stable but non-crashing
            r["marketCapNumeric"] = mc_num if mc_num is not None else 0.0

        # Valuation leader: lowest positive P/E
        val_candidates = [r for r in rows if (r.get("peNumeric") is not None and r.get("peNumeric") > 0)]
        if val_candidates:
            valuation_leader = min(val_candidates, key=lambda x: x.get("peNumeric", float("inf")))

        # Income leader: highest dividend yield
        inc_candidates = [r for r in rows if r.get("dividendYieldNumeric") is not None]
        if inc_candidates:
            income_leader = max(inc_candidates, key=lambda x: x.get("dividendYieldNumeric", 0.0))

        # Size leader: largest numeric market cap
        size_candidates = [r for r in rows if r.get("marketCapNumeric") is not None]
        if size_candidates:
            size_leader = max(size_candidates, key=lambda x: x.get("marketCapNumeric", 0.0))

        if valuation_leader:
            interpretation.append(f"{valuation_leader['name']} has the lowest valuation based on P/E among the compared stocks.")
        if income_leader:
            interpretation.append(f"{income_leader['name']} offers the highest dividend yield in this group.")
        if size_leader:
            interpretation.append(f"{size_leader['name']} is the largest company by reported market capitalisation.")

        # Growth candidate: highest P/E (market pricing in growth)
        growth_candidates = [r for r in val_candidates]  # reuse filtered P/E-positive set
        if growth_candidates:
            growth_candidate = max(growth_candidates, key=lambda x: x.get("peNumeric", 0.0))

        if valuation_leader:
            conclusion_lines.append(f"- Valuation leader: {valuation_leader['name']} (lowest P/E among peers).")
        if income_leader:
            conclusion_lines.append(f"- Income leader: {income_leader['name']} (highest dividend yield).")
        if growth_candidate:
            conclusion_lines.append(
                f"- Growth candidate: {growth_candidate['name']} (higher P/E suggests the market is pricing in more growth; validate with your own research)."
            )
        if not conclusion_lines:
            conclusion_lines.append("- No clear standouts on valuation, dividends, or size based on available data.")
    except Exception:
        # If anything goes wrong in leader/interpretation logic, fall back to a neutral explanation
        interpretation = []
        valuation_leader = None
        income_leader = None
        size_leader = None
        growth_candidate = None
        conclusion_lines = [
            "- Comparison signals are mixed or temporarily unavailable based on the fetched data.",
            "- Consider reviewing each stock's fundamentals and your own risk profile before deciding.",
        ]

    return {
        "rows": rows,
        "leaders": {
            "valuation_leader": valuation_leader,
            "income_leader": income_leader,
            "size_leader": size_leader,
            "growth_candidate": growth_candidate,
        },
        "interpretation": interpretation,
        "conclusion": conclusion_lines,
    }


async def _portfolio_allocation_analysis(allocs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not allocs:
        return None

    from app.services.stock_service import get_stock_detail

    # Normalize weights
    weights = [float(a["weight_percent"]) for a in allocs if a.get("symbol")]
    total = sum(weights) if weights else 0.0
    if total <= 0:
        return None

    normalized = [{"symbol": a["symbol"], "weight": float(a["weight_percent"]) / total} for a in allocs]

    # Fetch details with timeout
    details: List[Dict[str, Any]] = []
    sector_breakdown: Dict[str, int] = {}
    for a in normalized[:15]:
        sym = _normalize_symbol_maybe(a["symbol"])
        if not sym:
            continue
        d = await _run_sync_with_timeout(get_stock_detail, sym, timeout_s=10.0)
        if not isinstance(d, dict) or d.get("error"):
            continue
        d_out = {"symbol": d.get("symbol") or sym, "price": d.get("price"), "sector": d.get("sector"), "pe": d.get("pe")}
        details.append(d_out)
        sec = (d_out.get("sector") or "N/A") if isinstance(d_out, dict) else "N/A"
        sector_breakdown[sec] = sector_breakdown.get(sec, 0) + 1

    if not details:
        return {"error": "Unable to fetch portfolio symbols. Please verify the names/symbols."}

    # Diversification score: 0–100 from Herfindahl index
    hhi = sum((a["weight"] ** 2) for a in normalized)
    div_score = max(0.0, min(1.0, 1.0 - hhi))
    diversification_score = round(div_score * 100.0, 1)

    # Risk heuristic: concentration-based
    max_w = max(a["weight"] for a in normalized)
    if max_w >= 0.6:
        risk_level = "High"
    elif max_w >= 0.4:
        risk_level = "Medium"
    else:
        risk_level = "Low"

    suggestions: List[str] = []
    if diversification_score < 55:
        suggestions.append("Portfolio looks concentrated. Consider adding uncorrelated sectors (e.g., FMCG/Pharma) to improve diversification.")
    if len(sector_breakdown) <= 2:
        suggestions.append("Sector exposure is narrow. Spreading across 3–5 sectors typically reduces drawdown risk.")
    if max_w >= 0.5:
        suggestions.append("One holding dominates the portfolio; consider trimming to reduce single-stock risk.")

    return {
        "title": "Portfolio Risk Analysis",
        "stocks": details,
        "sector_breakdown": sector_breakdown,
        "diversification_score": diversification_score,
        "risk_level": risk_level,
        "suggestions": " ".join(suggestions) if suggestions else "Diversification looks reasonable. Maintain discipline with position sizing.",
        "allocations": [{"symbol": a["symbol"], "weight_percent": round(a["weight"] * 100, 2)} for a in normalized],
    }


async def handle_chat_query(
    query: str,
    *,
    context: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Returns:
        (response_payload, new_context_updates)
    """
    ctx = context or {}
    q = (query or "").strip()
    if not q:
        return (
            {"message": "Ask a question about stocks, RSI, comparison, portfolio, or market news."},
            {},
        )

    # Portfolio allocation detection (highest priority when user pastes weights)
    allocs = _extract_portfolio_allocations(q)
    if allocs:
        portfolio_result = await _portfolio_allocation_analysis(allocs)
        if isinstance(portfolio_result, dict) and portfolio_result.get("error"):
            return _chat_response({"source": "portfolio_analysis", "result": portfolio_result, "query": q}, {})
        return _chat_response(
            {"source": "portfolio_analysis", "result": portfolio_result, "query": q},
            {"last_intent": "portfolio_analysis", "last_portfolio_allocations": allocs},
        )

    classified = classify_intent(q, context=ctx)
    intent = classified.intent
    symbols = classified.symbols
    primary_symbol = classified.primary_symbol
    indicator_type = classified.indicator_type

    # Use follow-up memory: if no symbol in query, use last_symbol from context
    if not primary_symbol and isinstance(ctx.get("last_symbol"), str):
        primary_symbol = ctx.get("last_symbol")
    # Normalize primary symbol to yfinance form if possible
    primary_symbol = _normalize_symbol_maybe(primary_symbol) if primary_symbol else None

    # Generic help only when no intent detected, no symbol, and no finance keyword
    if intent == "unknown" and not has_finance_signal(q) and not primary_symbol and not ctx.get("last_symbol"):
        return (
            {"message": "I can help with: stock analysis, RSI/MACD, comparisons, portfolio risk, market news, or macro data. What would you like to know?"},
            {},
        )

    # Symbol-required intents: never analyze a random stock; require resolved symbol
    SYMBOL_REQUIRED_INTENTS = {
        "technical_indicator",
        "prediction",
        "advisor_recommendation",
        "buy_decision",
        "stock_analysis",
    }
    raw_parser_symbols = get_raw_parser_symbols(q, context=ctx)
    if intent in SYMBOL_REQUIRED_INTENTS and not primary_symbol:
        if raw_parser_symbols:
            return (
                {"message": "I could not identify the stock symbol. Please specify the company."},
                {},
            )
        # No symbol mentioned at all
        if intent == "technical_indicator":
            return ({"message": "Which stock should I run indicators for? Example: What does RSI say about INFY?"}, {})
        if intent == "prediction":
            return ({"message": "Which stock should I run the prediction model for? Example: Expected return of TCS."}, {})
        if intent in {"advisor_recommendation", "buy_decision"}:
            return ({"message": "Which stock should I recommend on? Example: Should I buy RELIANCE?"}, {})
        if intent == "stock_analysis":
            return ({"message": "Which stock should I analyze? Example: Analyze ICICI Bank."}, {})

    # Pull previous context
    last_symbols = ctx.get("last_symbols") if isinstance(ctx.get("last_symbols"), list) else None
    last_portfolio_allocs = ctx.get("last_portfolio_allocations") if isinstance(ctx.get("last_portfolio_allocations"), list) else None

    # ---- Routing ----

    # Growth potential comparison (uses AI prediction + simple momentum)
    if intent == "growth_comparison":
        compare_syms = list(symbols) if symbols else []
        if len(compare_syms) < 2:
            return (
                {"message": "Please specify the stocks to compare for growth potential. For example: `Which stock has better growth potential: TCS or INFY?`"},
                {},
            )
        from app.services.advisor_v2.prediction_engine import ensemble_forecast
        from app.services.stock_service import calculate_macd

        # Resolve symbols; do NOT fall back to last_symbols for growth queries
        s1 = _normalize_symbol_maybe(compare_syms[0])
        s2 = _normalize_symbol_maybe(compare_syms[1])
        if not s1 or not s2:
            return (
                {"message": "I could not identify the stock symbols. Please specify the companies clearly."},
                {},
            )

        async def _forecast(sym: str):
            f = await _run_sync_with_timeout(ensemble_forecast, sym, timeout_s=10.0)
            m = await _run_sync_with_timeout(calculate_macd, sym, timeout_s=10.0)
            er = None
            conf = None
            if isinstance(f, dict):
                er = f.get("expected_return")
                cobj = f.get("confidence") or {}
                conf = cobj.get("score")
            mom_score = 0.5
            if isinstance(m, dict) and not m.get("error"):
                trend = m.get("trend")
                if trend == "bullish":
                    mom_score = 1.0
                elif trend == "bearish":
                    mom_score = 0.0
            return {"expected_return": er, "confidence": conf, "momentum": mom_score}

        a, b = await _forecast(s1), await _forecast(s2)

        def _safe(v):
            try:
                return float(v)
            except Exception:
                return None

        er1, er2 = _safe(a.get("expected_return")), _safe(b.get("expected_return"))
        m1, m2 = _safe(a.get("momentum")), _safe(b.get("momentum"))
        c1, c2 = _safe(a.get("confidence")), _safe(b.get("confidence"))

        score1 = (er1 or 0.0) + 0.1 * (m1 or 0.5) + 0.05 * (c1 or 0.5)
        score2 = (er2 or 0.0) + 0.1 * (m2 or 0.5) + 0.05 * (c2 or 0.5)

        name1 = s1.replace(".NS", "").replace(".BO", "")
        name2 = s2.replace(".NS", "").replace(".BO", "")

        def _fmt_pct(x):
            return f"{x*100:+.2f}%" if x is not None else "N/A"

        lines = [
            f"Growth Potential – {name1} vs {name2}",
            "",
            f"{name1}:",
            f"Expected Return: {_fmt_pct(er1)}",
            f"Momentum Score: {m1 if m1 is not None else 'N/A'}",
            f"AI Confidence: {f'{(c1 or 0.0)*100:.1f}%' if c1 is not None else 'N/A'}",
            "",
            f"{name2}:",
            f"Expected Return: {_fmt_pct(er2)}",
            f"Momentum Score: {m2 if m2 is not None else 'N/A'}",
            f"AI Confidence: {f'{(c2 or 0.0)*100:.1f}%' if c2 is not None else 'N/A'}",
            "",
        ]

        if score1 > score2:
            conclusion = f"On these signals, {name1} shows stronger growth potential than {name2}."
        elif score2 > score1:
            conclusion = f"On these signals, {name2} shows stronger growth potential than {name1}."
        else:
            conclusion = f"On these signals, both {name1} and {name2} look similar on growth potential."

        lines.extend(
            [
                "Conclusion:",
                conclusion,
                "Use this as probabilistic guidance from the models, not a guarantee; always combine with fundamentals and risk tolerance.",
            ]
        )

        return ({"message": "\n".join(lines)}, {"last_symbols": [s1, s2], "last_intent": "growth_comparison"})

    # Long-term comparison (fundamentals + AI growth outlook)
    if intent == "long_term_comparison":
        compare_syms = list(symbols) if symbols else []
        if len(compare_syms) < 2 and last_symbols:
            compare_syms = list(last_symbols)[:2]
        if len(compare_syms) < 2:
            return (
                {
                    "message": "Please specify two stocks for long-term comparison. For example: `Compare TCS and INFY for long-term investment.`"
                },
                {},
            )

        from app.services.advisor_v2.prediction_engine import ensemble_forecast

        s1 = _normalize_symbol_maybe(compare_syms[0])
        s2 = _normalize_symbol_maybe(compare_syms[1])
        if not s1 or not s2:
            return (
                {"message": "I could not identify the stock symbols. Please specify the companies clearly."},
                {},
            )

        comp = await _comparison_result([s1, s2])

        async def _lt_forecast(sym: str):
            f = await _run_sync_with_timeout(ensemble_forecast, sym, horizon="medium", timeout_s=12.0)
            er = None
            conf = None
            if isinstance(f, dict):
                er = f.get("expected_return")
                cobj = f.get("confidence") or {}
                conf = cobj.get("score")
            return {"expected_return": er, "confidence": conf}

        f1, f2 = await _lt_forecast(s1), await _lt_forecast(s2)

        def _safe(v):
            try:
                return float(v)
            except Exception:
                return None

        er1 = _safe(f1.get("expected_return"))
        er2 = _safe(f2.get("expected_return"))
        c1 = _safe(f1.get("confidence"))
        c2 = _safe(f2.get("confidence"))

        name1 = (comp.get("name1") if isinstance(comp, dict) else s1 or "").replace(".NS", "").replace(".BO", "")
        name2 = (comp.get("name2") if isinstance(comp, dict) else s2 or "").replace(".NS", "").replace(".BO", "")

        def _fmt_pct(x):
            return f"{x*100:+.2f}%" if x is not None else "N/A"

        lines = [
            f"Long-Term Comparison – {name1} vs {name2}",
            "",
            "Growth outlook (AI models):",
            f"- {name1}: expected return {_fmt_pct(er1)} (confidence {f'{(c1 or 0.0)*100:.0f}%' if c1 is not None else 'N/A'})",
            f"- {name2}: expected return {_fmt_pct(er2)} (confidence {f'{(c2 or 0.0)*100:.0f}%' if c2 is not None else 'N/A'})",
        ]

        if isinstance(comp, dict):
            pe1 = comp.get("pe1")
            pe2 = comp.get("pe2")
            div1 = comp.get("dividendYield1") or 0
            div2 = comp.get("dividendYield2") or 0
            mc1 = comp.get("marketCap1")
            mc2 = comp.get("marketCap2")

            lines.extend(
                [
                    "",
                    "Valuation & Dividends:",
                    f"- {name1}: P/E {pe1 if pe1 is not None else 'N/A'}, dividend yield {div1}%",
                    f"- {name2}: P/E {pe2 if pe2 is not None else 'N/A'}, dividend yield {div2}%",
                ]
            )

            if mc1 or mc2:
                stab_note = None
                try:
                    if mc1 and mc2:
                        if float(mc1) > float(mc2):
                            stab_note = f"{name1} is larger by market cap, which can mean more stability but slower growth."
                        elif float(mc2) > float(mc1):
                            stab_note = f"{name2} is larger by market cap, which can mean more stability but slower growth."
                    elif mc1 or mc2:
                        bigger = name1 if mc1 else name2
                        stab_note = f"{bigger} has the larger reported market cap, which can indicate relatively more stability."
                except Exception:
                    stab_note = None
                lines.extend(["", "Stability (size):"])
                lines.append(f"- {stab_note}" if stab_note else "- Market cap data is limited; treat both as similar on stability from this view.")

            interp = comp.get("interpretation") or []
            if interp:
                lines.extend(["", "Fundamental notes:"] + [f"- {x}" for x in interp])

            pref = (comp.get("recommendation") or {}).get("preferred")
            pref_reason = (comp.get("recommendation") or {}).get("reason")
        else:
            pref = None
            pref_reason = None

        lines.append("")
        lines.append("Conclusion:")

        growth_pref = None
        if er1 is not None and er2 is not None:
            if er1 > er2:
                growth_pref = name1
            elif er2 > er1:
                growth_pref = name2

        if pref and growth_pref and pref == growth_pref:
            lines.append(f"- On both growth outlook and current valuation metrics, {pref} looks somewhat better suited for long-term holding.")
        elif pref and growth_pref and pref != growth_pref:
            lines.append(
                f"- Models see stronger long-term growth potential in {growth_pref}, while valuation/dividend metrics slightly favour {pref}. "
                "Choose based on whether you prioritise growth or current income/valuation."
            )
        elif pref:
            lines.append(f"- Fundamentals (valuation/dividends) modestly favour {pref}. {pref_reason or ''}")
        elif growth_pref:
            lines.append(f"- On the AI growth outlook alone, {growth_pref} has a slight edge. Treat this as probabilistic, not guaranteed.")
        else:
            lines.append("- Both look broadly similar on the available growth and valuation signals; consider diversification or your sector/stock preference.")

        lines.append("Always align with your risk tolerance, horizon, and diversification plan; this is not financial advice.")

        return (
            {
                "message": "\n".join(lines),
                "result": {"comparison": comp, "forecasts": {name1: f1, name2: f2}},
            },
            {"last_symbols": [s1, s2], "last_intent": "long_term_comparison"},
        )

    # comparison (valuation/dividend style)
    if intent == "comparison":
        try:
            # Use only explicitly detected symbols; for follow-ups with no symbols, reuse previous set.
            compare_syms = list(symbols) if symbols else []
            if not compare_syms and last_symbols:
                compare_syms = list(last_symbols)
            if len(compare_syms) < 2:
                return (
                    {"message": "Please provide at least two stocks to compare. Example: Compare TCS INFY and RELIANCE."},
                    {},
                )
            # Resolve all to .NS/.BO; never use unresolved tokens
            resolved_syms: List[str] = []
            for s in compare_syms:
                rs = _normalize_symbol_maybe(s)
                if rs:
                    resolved_syms.append(rs)
            if len(resolved_syms) < 2:
                return (
                    {"message": "I could not identify at least two valid stock symbols. Please specify the companies clearly."},
                    {},
                )

            # If exactly two, preserve existing detailed pairwise structure for compatibility.
            if len(resolved_syms) == 2:
                comp = await _comparison_result(resolved_syms)
                if comp:
                    return _chat_response(
                        {"source": "compare_stocks", "result": comp, "query": q},
                        {
                            "last_symbols": [comp.get("symbol1"), comp.get("symbol2")],
                            "last_symbol": comp.get("symbol1"),
                            "last_intent": "comparison",
                        },
                    )
                return _chat_response(
                    {
                        "source": "compare_stocks",
                        "result": {"error": "Unable to fetch comparison data for one or both symbols."},
                        "query": q,
                    },
                    {"last_intent": "comparison"},
                )

            # Multi-stock comparison (3+)
            multi = await _multi_comparison_result(resolved_syms)
            if not isinstance(multi, dict):
                return _chat_response(
                    {
                        "source": "compare_stocks",
                        "result": {"error": "comparison_unavailable"},
                        "message": "Comparison data is temporarily unavailable. Please try again.",
                        "query": q,
                    },
                    {"last_intent": "comparison"},
                )

            rows = multi.get("rows") or []
            if len(rows) < 2:
                return (
                    {"message": "Please provide at least two valid stocks to compare."},
                    {},
                )

            def _fmt_price(x: Any) -> str:
                try:
                    return f"₹{float(x):,.2f}"
                except Exception:
                    return "N/A"

            def _fmt_pe(x: Any) -> str:
                try:
                    return f"{float(x):.1f}"
                except Exception:
                    return "N/A"

            def _fmt_div(x: Any) -> str:
                try:
                    return f"{float(x):.1f}%"
                except Exception:
                    return "N/A"

            header = f"{'Stock':<12} {'Price':>10} {'P/E':>8} {'Dividend':>10} {'Sector':<20}"
            sep = "-" * len(header)
            lines: List[str] = []
            lines.append("Stock Comparison")
            lines.append("")
            lines.append(header)
            lines.append(sep)
            for r in rows:
                name = str(r.get("name") or r.get("symbol") or "")[:12]
                price = _fmt_price(r.get("price"))
                pe = _fmt_pe(r.get("pe"))
                dy = _fmt_div(r.get("dividendYield"))
                sector = str(r.get("sector") or "")[:20]
                lines.append(f"{name:<12} {price:>10} {pe:>8} {dy:>10} {sector:<20}")

            interp = multi.get("interpretation") or []
            if interp:
                lines.extend(["", "Interpretation:"] + [f"• {x}" for x in interp])

            concl = multi.get("conclusion") or []
            if concl:
                lines.extend(["", "Conclusion:"] + concl)

            lines.append("")
            lines.append("Use this as a high-level comparison of valuation, income, and size only; always combine with your own research and risk profile.")

            # Track last_symbols for follow-up questions
            last_syms_ctx = [str(r.get("symbol") or "") for r in rows if r.get("symbol")]

            return _chat_response(
                {
                    "source": "compare_stocks",
                    "result": multi,
                    "message": "\n".join(lines),
                    "query": q,
                },
                {"last_symbols": last_syms_ctx, "last_intent": "comparison"},
            )
        except Exception:
            # Final guard so that comparison failures never crash the advisor orchestrator
            return _chat_response(
                {
                    "source": "compare_stocks",
                    "result": {"error": "comparison_engine_error"},
                    "message": "Comparison engine encountered an issue. Please try again.",
                    "query": q,
                },
                {"last_intent": "comparison"},
            )

    # Technical indicators
    if intent == "technical_indicator":
        sym = primary_symbol or (ctx.get("last_symbol") if isinstance(ctx.get("last_symbol"), str) else None)
        sym = _normalize_symbol_maybe(sym) if sym else None
        if not sym:
            return ({"message": "Which stock should I run indicators for? Example: `What does RSI say about INFY?`"}, {})

        from app.services.stock_service import calculate_macd, calculate_moving_averages, calculate_rsi

        if indicator_type == "rsi":
            r = await _run_sync_with_timeout(calculate_rsi, sym, timeout_s=10.0)
            res = r or {"error": "No RSI data"}
            if isinstance(res, dict):
                res["symbol"] = sym
            return _chat_response({"source": "rsi", "result": res, "query": q}, {"last_symbol": sym, "last_intent": "technical_indicator"})
        if indicator_type == "macd":
            r = await _run_sync_with_timeout(calculate_macd, sym, timeout_s=10.0)
            if isinstance(r, dict) and not r.get("error"):
                trend = r.get("trend")
                final = "bullish" if trend == "bullish" else "bearish" if trend == "bearish" else "neutral"
                r["final_signal"] = final
                r["final_interpretation"] = f"MACD trend {trend or 'neutral'} → final technical signal: {final}."
            res = r or {"error": "No MACD data"}
            res["symbol"] = sym
            return _chat_response({"source": "macd", "result": res, "query": q}, {"last_symbol": sym, "last_intent": "technical_indicator"})
        if indicator_type == "moving_averages":
            r = await _run_sync_with_timeout(calculate_moving_averages, sym, timeout_s=10.0)
            res = r or {"error": "No moving averages data"}
            res["symbol"] = sym
            return _chat_response({"source": "moving_averages", "result": res, "query": q}, {"last_symbol": sym, "last_intent": "technical_indicator"})

        # "technical" => combined payload (frontend supports technical_analysis formatting)
        rsi = await _run_sync_with_timeout(calculate_rsi, sym, timeout_s=10.0)
        macd = await _run_sync_with_timeout(calculate_macd, sym, timeout_s=10.0)
        ma = await _run_sync_with_timeout(calculate_moving_averages, sym, timeout_s=10.0)
        interp: List[str] = []
        if isinstance(rsi, dict) and rsi.get("signal"):
            sig = rsi.get("signal")
            if sig == "overbought":
                interp.append(f"RSI {rsi.get('rsi')} suggests overbought—caution on fresh longs.")
            elif sig == "oversold":
                interp.append(f"RSI {rsi.get('rsi')} suggests oversold—potential bounce zone.")
            else:
                interp.append(f"RSI {rsi.get('rsi')} is neutral.")
        if isinstance(ma, dict) and ma.get("signal_sma200"):
            if ma.get("signal_sma200") == "above":
                interp.append("Price is above the 200-day moving average (bullish long-term structure).")
            else:
                interp.append("Price is below the 200-day moving average (weak long-term structure).")
        if isinstance(macd, dict) and macd.get("trend"):
            interp.append(f"MACD momentum looks {macd.get('trend')}.")

        final_signal = (
            "bearish"
            if any("overbought" in (s or "").lower() or "macd bearish" in (s or "").lower() for s in interp)
            else "bullish"
            if any("oversold" in (s or "").lower() or "bullish" in (s or "").lower() for s in interp)
            else "neutral"
        )

        tech_result = {
            "symbol": sym,
            "rsi": rsi if isinstance(rsi, dict) and not rsi.get("error") else None,
            "macd": macd if isinstance(macd, dict) and not macd.get("error") else None,
            "moving_averages": ma if isinstance(ma, dict) and not ma.get("error") else None,
            "interpretation": interp,
            "final_signal": final_signal,
        }
        return _chat_response(
            {"source": "technical_analysis", "result": tech_result, "query": q},
            {"last_symbol": sym, "last_intent": "technical_indicator"},
        )

    # Market news (news_query maps to same handler)
    if intent in {"market_news", "news_query"}:
        market = "BSE" if "bse" in q.lower() or "sensex" in q.lower() else "NSE"
        items = await _run_sync_with_timeout(get_market_news, market, timeout_s=10.0)
        if not items:
            mock = sample_mock_news(market=market, k=5)
            news_list = mock.get("news", [])
            msg_lines = [f"Latest {market} headlines:", ""] + [f"• {(n.get('title') or n.get('source', ''))}" for n in (news_list or [])[:5]]
            return _chat_response(
                {"source": "market_news", "result": {"news": mock["news"], "market": market, "summary": mock["summary"], "interpretation": "\n".join(msg_lines)}, "query": q},
                {"last_intent": "market_news"},
            )
        msg_lines = [f"Latest {market} headlines:", ""] + [f"• {n.get('title', '')}" for n in (items or [])[:8]]
        return _chat_response(
            {"source": "market_news", "result": {"news": items, "market": market, "interpretation": "\n".join(msg_lines)}, "query": q},
            {"last_intent": "market_news"},
        )

    # Macro / fallback finance (macro_query maps to same handler)
    if intent in {"macro_economics", "macro_query"}:
        from app.services.macro_service import get_gdp, get_inflation, get_repo_rate

        low = q.lower()
        if "repo" in low or "rbi" in low:
            r = await _run_sync_with_timeout(get_repo_rate, timeout_s=10.0)
            if isinstance(r, dict) and not r.get("error"):
                msg = f"RBI Repo Rate: {r.get('repo_rate', 'N/A')}% (last updated: {r.get('last_updated', 'N/A')})"
            else:
                msg = "Unable to fetch repo rate."
            return _chat_response({"source": "macro", "result": r or {"error": "Unable to fetch repo rate"}, "message": msg, "query": q}, {})
        if "inflation" in low:
            r = await _run_sync_with_timeout(get_inflation, timeout_s=10.0)
            if isinstance(r, list) and r:
                msg = "India CPI Inflation (recent):\n" + "\n".join(f"  {y.get('year', '')}: {y.get('inflation', 'N/A')}%" for y in r[:3])
            elif isinstance(r, dict) and r.get("error"):
                msg = r.get("error", "Unable to fetch inflation data.")
            else:
                msg = "Unable to fetch inflation data."
            return _chat_response({"source": "macro", "result": r or {"error": "Unable to fetch inflation data"}, "message": msg, "query": q}, {})
        if "gdp" in low:
            r = await _run_sync_with_timeout(get_gdp, timeout_s=10.0)
            if isinstance(r, list) and r:
                msg = "India GDP growth (recent):\n" + "\n".join(f"  {y.get('year', '')}: {y.get('gdp_growth', 'N/A')}%" for y in r[:3])
            elif isinstance(r, dict) and r.get("error"):
                msg = r.get("error", "Unable to fetch GDP data.")
            else:
                msg = "Unable to fetch GDP data."
            return _chat_response({"source": "macro", "result": r or {"error": "Unable to fetch GDP data"}, "message": msg, "query": q}, {})
        return (
            {
                "message": "I can help with RBI repo rate, inflation, GDP growth, taxation basics, and market context. Ask a specific macro question (e.g., `current repo rate`).",
            },
            {},
        )

    # Market regime / context
    if intent == "market_regime":
        from app.services.advisor_v4.regime_detection import detect_market_regime
        from app.services.sector_service import get_all_sectors_summary

        regime = await _run_sync_with_timeout(detect_market_regime, "^NSEI", timeout_s=10.0)
        sectors = await _run_sync_with_timeout(get_all_sectors_summary, timeout_s=10.0)
        mr = (regime or {}).get("market_regime")
        interpretation = (
            "NIFTY trend looks sideways with moderate volatility."
            if mr == "sideways_market"
            else "Market trend is positive with strengthening breadth."
            if mr == "bull_market"
            else "Market trend is weak with elevated downside risk."
            if mr == "bear_market"
            else "Unable to confidently classify the current market regime."
        )
        risk_factors = "Regime signals are based on recent index moves and volatility; sudden macro events can change conditions quickly."
        conclusion = "Use the regime as a backdrop for position sizing (higher cash in bearish regimes, more deployment in bullish ones)."
        result = {
            "analysis": "Market Regime Overview",
            "metrics": {"regime": regime, "top_sectors": (sectors or [])[:5]},
            "interpretation": interpretation,
            "risk_factors": risk_factors,
            "conclusion": conclusion,
        }
        message = _format_market_regime_message(regime or {}, interpretation, risk_factors, conclusion)
        return _chat_response({"source": "market_regime", "result": result, "query": q}, {"last_intent": "market_regime"})

    # Market screeners (multi-stock scans)
    if intent in {"momentum_scan", "breakout_scan", "mean_reversion_scan"}:
        from app.services.advisor_v4.market_screener import scan_breakouts, scan_mean_reversion, scan_momentum

        if intent == "momentum_scan":
            res = await scan_momentum(limit=5)
            confirmed = (res or {}).get("confirmed") or []
            watch = (res or {}).get("watchlist") or []
            if confirmed:
                lines = ["Strong Momentum Stocks", ""]
                for i, r in enumerate(confirmed, 1):
                    sym = str(r.symbol).replace(".NS", "").replace(".BO", "")
                    lines.append(f"{i}. {sym} → {r.notes}")
                lines.extend(["", "Interpretation:", "These stocks show strong momentum based on RSI and trend signals."])
                return ({"message": "\n".join(lines)}, {"last_intent": "momentum_scan"})

            if watch:
                lines = ["Strong Momentum Watchlist", "", "No strong momentum signals detected today.", "", "Closest candidates:", ""]
                for i, r in enumerate(watch, 1):
                    sym = str(r.symbol).replace(".NS", "").replace(".BO", "")
                    lines.append(f"{i}. {sym} → {r.notes}")
                lines.extend(["", "Interpretation:", "Momentum is building in a few names, but confirmation signals have not yet appeared."])
                return ({"message": "\n".join(lines)}, {"last_intent": "momentum_scan"})

            return ({"message": "Market momentum is currently weak across the monitored stock universe."}, {"last_intent": "momentum_scan"})

        if intent == "mean_reversion_scan":
            res = await scan_mean_reversion(limit=5)
            confirmed = (res or {}).get("confirmed") or []
            watch = (res or {}).get("watchlist") or []
            if confirmed:
                lines = ["Mean Reversion Opportunities (Oversold Candidates)", ""]
                for i, r in enumerate(confirmed, 1):
                    sym = str(r.symbol).replace(".NS", "").replace(".BO", "")
                    lines.append(f"{i}. {sym} → {r.notes}")
                lines.extend(["", "Interpretation:", "These names are in an oversold zone (low RSI). Mean reversion setups work best when the broader trend and support levels align."])
                return ({"message": "\n".join(lines)}, {"last_intent": "mean_reversion_scan"})

            if watch:
                lines = ["Mean Reversion Watchlist", "", "No oversold (RSI<35) candidates detected today.", "", "Closest candidates:", ""]
                for i, r in enumerate(watch, 1):
                    sym = str(r.symbol).replace(".NS", "").replace(".BO", "")
                    lines.append(f"{i}. {sym} → {r.notes}")
                lines.extend(["", "Interpretation:", "Some stocks are approaching oversold territory, but none are deeply oversold yet."])
                return ({"message": "\n".join(lines)}, {"last_intent": "mean_reversion_scan"})

            return ({"message": "Market momentum is currently weak across the monitored stock universe."}, {"last_intent": "mean_reversion_scan"})

        res = await scan_breakouts(limit=5)
        confirmed = (res or {}).get("confirmed") or []
        watch = (res or {}).get("watchlist") or []

        if confirmed:
            lines = ["Breakout Signals (Monitored Universe)", ""]
            for i, r in enumerate(confirmed, 1):
                sym = str(r.symbol).replace(".NS", "").replace(".BO", "")
                lines.append(f"{i}. {sym} → {r.notes}")
            lines.extend(["", "Interpretation:", "These stocks show potential breakout behavior based on MA cross signals and/or MACD crossovers."])
            return ({"message": "\n".join(lines)}, {"last_intent": "breakout_scan"})

    # AI buy signals screener (model + momentum)
    if intent == "ai_buy_signals":
        from app.services.advisor_v4.market_screener import scan_ai_buy_signals

        rows = await scan_ai_buy_signals(limit=5)
        if not rows:
            return (
                {
                    "message": "I couldn't find strong AI-backed buy signals in the monitored universe today. The models may see limited edge right now."
                },
                {"last_intent": "ai_buy_signals"},
            )

        def _fmt_er(x):
            try:
                return f"{float(x)*100:+.1f}%"
            except Exception:
                return "N/A"

        def _fmt_mom(m):
            try:
                mv = float(m)
            except Exception:
                return "neutral"
            if mv >= 0.85:
                return "strong bullish"
            if mv >= 0.65:
                return "bullish"
            if mv <= 0.25:
                return "bearish"
            return "neutral"

        lines = ["Strong AI Buy Signals (short-term)", ""]
        for i, r in enumerate(rows, 1):
            sym = str(r.symbol).replace(".NS", "").replace(".BO", "")
            er = _fmt_er(getattr(r, "expected_return", None))
            mom = _fmt_mom(getattr(r, "momentum", None))
            lines.append(f"{i}. {sym} → expected return {er}, momentum {mom}")
        lines.extend(
            [
                "",
                "Interpretation:",
                "These names combine positive model-predicted upside with supportive momentum. Use this as a watchlist, not a blind buy list.",
            ]
        )
        return ({"message": "\n".join(lines)}, {"last_intent": "ai_buy_signals"})

    # Static list of AI sector beneficiaries
    if intent == "ai_sector_beneficiaries":
        from app.services.advisor_v4.market_screener import get_ai_sector_beneficiaries

        rows = get_ai_sector_beneficiaries()
        if not rows:
            return ({"message": "I couldn't load the curated AI-beneficiary list right now. Please try again later."}, {"last_intent": "ai_sector_beneficiaries"})

        lines = ["AI Beneficiary Stocks (India IT & digital)", ""]
        for r in rows:
            sym = str((r or {}).get("symbol", "")).replace(".NS", "").replace(".BO", "")
            reason = (r or {}).get("reason", "")
            lines.append(f"- {sym}: {reason}")
        lines.extend(
            [
                "",
                "Note:",
                "This is a qualitative, curated view of likely AI beneficiaries in Indian markets, not a ranking or guarantee of outperformance.",
            ]
        )
        return ({"message": "\n".join(lines)}, {"last_intent": "ai_sector_beneficiaries"})

        if watch:
            lines = ["Breakout Watchlist", "", "No confirmed breakout signals detected today.", "", "Closest candidates:", ""]
            for i, r in enumerate(watch, 1):
                sym = str(r.symbol).replace(".NS", "").replace(".BO", "")
                lines.append(f"{i}. {sym} → {r.notes}")
            lines.extend(["", "Interpretation:", "Momentum is building in several stocks but confirmation signals have not yet appeared."])
            return ({"message": "\n".join(lines)}, {"last_intent": "breakout_scan"})

        return ({"message": "Market momentum is currently weak across the monitored stock universe."}, {"last_intent": "breakout_scan"})

    # Institutional flow / volume intelligence
    if intent in {"institutional_activity", "volume_scan", "accumulation_scan", "sector_flow_scan"}:
        from app.services.advisor_v4.market_screener import scan_accumulation, scan_sector_flow, scan_unusual_volume
        from app.services.advisor_v4.smart_money_tracker import detect_smart_money

        def _clean(sym: str) -> str:
            return (sym or "").replace(".NS", "").replace(".BO", "")

        def _signal_from_z(z: float | None) -> str:
            if z is None:
                return "Unknown"
            if z > 1.5:
                return "Strong institutional participation"
            if z > 0.5:
                return "Moderate accumulation"
            if z >= -0.5:
                return "Normal trading activity"
            return "Weak participation"

        # Sector flow detection
        if intent == "sector_flow_scan":
            ql = q.lower()
            sector = "IT" if "it stocks" in ql else "BANKING" if "banking stocks" in ql else "ENERGY" if "energy stocks" in ql else "IT"
            rows = await scan_sector_flow(sector)
            if not rows:
                return ({"message": "No strong institutional flow signals detected in the monitored stocks today."}, {"last_intent": "sector_flow_scan"})
            lines = [f"Sector Institutional Activity – {sector}", ""]
            for r in rows:
                sym = _clean(r.symbol)
                lbl = r.label.replace("_", " ")
                lines.append(f"{sym} → {lbl}")
            lines.append("")
            lines.append("Interpretation:")
            lines.append("This summary is based on volume z-scores (unusual volume relative to recent history) and is a proxy for institutional participation.")
            return ({"message": "\n".join(lines)}, {"last_intent": "sector_flow_scan"})

        # Market-wide unusual volume screener
        if intent == "volume_scan":
            rows = await scan_unusual_volume(limit=5)
            if not rows:
                return ({"message": "No strong institutional flow signals detected in the monitored stocks today."}, {"last_intent": "volume_scan"})
            lines = ["Unusual Volume (Monitored Universe)", ""]
            for i, r in enumerate(rows, 1):
                sym = _clean(r.symbol)
                z = r.volume_z
                z_str = f"{z:.2f}" if isinstance(z, (int, float)) else "N/A"
                lines.append(f"{i}. {sym} → Volume Z-Score {z_str} ({_signal_from_z(z)})")
            return ({"message": "\n".join(lines)}, {"last_intent": "volume_scan"})

        # Accumulation scan
        if intent == "accumulation_scan":
            rows = await scan_accumulation(limit=5)
            if not rows:
                return ({"message": "No strong institutional flow signals detected in the monitored stocks today."}, {"last_intent": "accumulation_scan"})
            lines = ["Accumulation Scan (Monitored Universe)", ""]
            for i, r in enumerate(rows, 1):
                sym = _clean(r.symbol)
                z = r.volume_z
                pc = r.price_change
                z_str = f"{z:.2f}" if isinstance(z, (int, float)) else "N/A"
                pc_str = f"{pc*100:+.2f}%" if isinstance(pc, (int, float)) else "N/A"
                lines.append(f"{i}. {sym} → z={z_str}, price_change={pc_str}")
            lines.extend(["", "Interpretation:", "High volume plus positive price action can indicate accumulation, but confirm with trend and news context."])
            return ({"message": "\n".join(lines)}, {"last_intent": "accumulation_scan"})

        # Single-stock institutional activity
        sym = primary_symbol or (ctx.get("last_symbol") if isinstance(ctx.get("last_symbol"), str) else None)
        sym = _normalize_symbol_maybe(sym) if sym else None
        if not sym:
            return ({"message": "Which stock should I check institutional activity for? Example: `Is there institutional buying in RELIANCE?`"}, {})
        sm = await _run_sync_with_timeout(detect_smart_money, sym, timeout_s=10.0)
        if not isinstance(sm, dict):
            return ({"message": "No strong institutional flow signals detected in the monitored stocks today."}, {"last_intent": "institutional_activity"})
        z = sm.get("volume_zscore")
        try:
            zf = float(z) if z is not None else None
        except Exception:
            zf = None
        z_str = f"{zf:.2f}" if isinstance(zf, (int, float)) else "N/A"
        signal = _signal_from_z(zf)
        interpretation = (
            "A high positive volume z-score suggests above-normal participation, often seen during institutional activity."
            if zf is not None and zf > 0.5
            else "Volume looks close to normal; there’s no strong evidence of unusual institutional participation from volume alone."
        )
        lines = [
            f"Institutional Activity – {_clean(sym)}",
            "",
            f"Volume Z-Score: {z_str}",
            "",
            "Signal:",
            signal,
            "",
            "Interpretation:",
            interpretation,
        ]
        return ({"message": "\n".join(lines)}, {"last_symbol": sym, "last_intent": "institutional_activity"})

    # Market-level intelligence
    if intent in {"market_insights", "market_risk", "market_trends"}:
        from app.services.advisor_v4.market_screener import (
            generate_market_insights,
            generate_market_risk_summary,
            generate_market_trend_summary,
        )

        def _clean(sym: str) -> str:
            return (sym or "").replace(".NS", "").replace(".BO", "")

        if intent == "market_insights":
            data = await generate_market_insights()
            if not data:
                return ({"message": "Market signals are currently mixed with no dominant trend."}, {"last_intent": "market_insights"})

            regime = data.get("market_regime", "mixed")
            moms = data.get("momentum_leaders") or []
            sectors = data.get("sector_flow") or []
            forecasts = data.get("ai_forecast_leaders") or []

            lines = ["AI Market Insights – Today", "", "Market Regime:", f"{str(regime).title()}", ""]
            lines.append("Momentum Leaders:")
            if moms:
                for r in moms[:3]:
                    sym = _clean(getattr(r, "symbol", "") or (r.get("symbol") if isinstance(r, dict) else ""))
                    note = getattr(r, "notes", None) or (r.get("notes") if isinstance(r, dict) else "")
                    lines.append(f"- {sym} → {note}".strip())
            else:
                lines.append("- None")
            lines.append("")
            lines.append("Institutional Flow:")
            if sectors:
                for sec, z in sectors[:2]:
                    lines.append(f"- {sec} → average volume z-score ~ {float(z):+.2f}")
            else:
                lines.append("- No strong accumulation signals")
            lines.append("")
            lines.append("AI Forecast Leaders:")
            if forecasts:
                for row in forecasts[:3]:
                    sym = _clean(row.get("symbol", ""))
                    er = row.get("expected_return")
                    try:
                        pct = float(er) * 100
                        lines.append(f"- {sym} → {pct:+.2f}%")
                    except Exception:
                        lines.append(f"- {sym}")
            else:
                lines.append("- Unavailable")
            return ({"message": "\n".join(lines)}, {"last_intent": "market_insights"})

        if intent == "market_risk":
            data = await generate_market_risk_summary()
            if not data:
                return ({"message": "Market signals are currently mixed with no dominant trend."}, {"last_intent": "market_risk"})
            regime = data.get("regime") or {}
            vol = (regime or {}).get("volatility_level")
            mr = (regime or {}).get("market_regime")
            acc_n = int(data.get("accumulation_count") or 0)

            lines = ["Market Risks – Today", ""]
            if vol and "high" in str(vol):
                lines.append("Rising volatility in index.")
            elif vol:
                lines.append(f"Volatility level: {vol}.")
            if mr and "bear" in str(mr):
                lines.append("Market regime leans bearish (downside risk elevated).")
            if not data.get("momentum_confirmed"):
                lines.append("Broad momentum leadership is limited (few strong trend signals).")
            if acc_n == 0:
                lines.append("Lack of strong institutional accumulation in monitored stocks.")
            lines.extend(["", "Conclusion:", "Investors should remain cautious and prioritize risk management (position sizing, stops, diversification)."])
            return ({"message": "\n".join(lines)}, {"last_intent": "market_risk"})

        data = await generate_market_trend_summary()
        if not data:
            return ({"message": "Market signals are currently mixed with no dominant trend."}, {"last_intent": "market_trends"})
        regime = data.get("regime") or {}
        mr = (regime or {}).get("market_regime")
        moms = data.get("momentum_leaders") or []
        sec_flow = data.get("sector_flow") or []

        lines = ["Emerging Market Trends", ""]
        if mr:
            lines.append(f"Backdrop: {str(mr).replace('_', ' ')}.")
            lines.append("")
        if sec_flow:
            # map limited sectors
            top = sec_flow[0]
            bottom = sec_flow[-1] if len(sec_flow) > 1 else None
            lines.append(f"{top[0].title()} showing relatively stronger participation.")
            if bottom:
                lines.append(f"{bottom[0].title()} showing weaker participation.")
        if moms:
            lines.append("")
            lines.append("Momentum leaders:")
            for r in moms[:3]:
                sym = _clean(getattr(r, "symbol", "") or (r.get("symbol") if isinstance(r, dict) else ""))
                note = getattr(r, "notes", None) or (r.get("notes") if isinstance(r, dict) else "")
                lines.append(f"- {sym} → {note}".strip())
        return ({"message": "\n".join(lines)}, {"last_intent": "market_trends"})

    # AI picks / highest predicted growth
    if intent == "ai_picks":
        from app.services.prediction_ranking_service import rank_by_expected_return

        ranking = await _run_sync_with_timeout(rank_by_expected_return, None, horizon="short", limit=10, timeout_s=25.0)
        if not isinstance(ranking, dict) or not ranking.get("ranked"):
            err_msg = "Could not compute predictions. Try again shortly."
            return _chat_response(
                {"source": "ai_picks", "result": {"ranked": []}, "message": err_msg, "query": q},
                {"last_intent": "ai_picks"},
            )
        ranked = ranking.get("ranked", [])[:10]
        horizon = ranking.get("horizon", "short")
        message = _format_ai_picks_message(ranked, horizon)
        result = {
            "analysis": "AI Picks by Predicted Growth",
            "metrics": {"horizon": horizon, "horizon_label": _horizon_label(horizon), "ranked": ranked},
            "interpretation": message,
            "risk_factors": "Based on historical price/volatility patterns only; not financial advice.",
            "conclusion": "Use as one input among many; diversify and size positions appropriately.",
        }
        return _chat_response({"source": "ai_picks", "result": result, "query": q}, {"last_intent": "ai_picks"})

    # Volume / smart money
    if intent == "volume_analysis":
        from app.services.advisor_v4.smart_money_tracker import detect_smart_money
        from app.services.stock_service import NIFTY_50_SYMBOLS

        sym = primary_symbol
        if sym:
            sm = await _run_sync_with_timeout(detect_smart_money, sym, timeout_s=10.0)
            return _chat_response({"source": "volume_analysis", "result": {"symbol": sym, "smart_money": sm}, "query": q}, {"last_symbol": sym, "last_intent": "volume_analysis"})

        # Screener mode: return top unusual-volume names from a small subset to stay fast.
        sample = NIFTY_50_SYMBOLS[:12]
        rows = []
        for s in sample:
            sm = await _run_sync_with_timeout(detect_smart_money, s, timeout_s=4.0)
            if isinstance(sm, dict) and sm.get("volume_zscore") is not None:
                rows.append({"symbol": s, **sm})
        rows.sort(key=lambda r: float(r.get("volume_zscore") or 0), reverse=True)
        return _chat_response(
            {"source": "volume_analysis", "result": {"screen": rows[:8], "note": "Screened a limited NIFTY subset for speed."}, "query": q},
            {"last_intent": "volume_analysis"},
        )

    # Prediction
    if intent == "prediction":
        sym = primary_symbol or (ctx.get("last_symbol") if isinstance(ctx.get("last_symbol"), str) else None)
        sym = _normalize_symbol_maybe(sym) if sym else None
        if not sym:
            return ({"message": "Which stock should I run the prediction model for? Example: `Predict price for RELIANCE`."}, {})
        from app.services.advisor_v2.prediction_engine import ensemble_forecast
        from app.services.stock_service import get_stock_quote

        # Horizon heuristic
        low = q.lower()
        horizon = "short"
        if "intraday" in low or "today" in low:
            horizon = "intraday"
        elif "medium" in low or "1 month" in low or "20" in low:
            horizon = "medium"

        forecast = await _run_sync_with_timeout(ensemble_forecast, sym, horizon=horizon, timeout_s=10.0)
        quote = await _run_sync_with_timeout(get_stock_quote, sym, timeout_s=10.0)

        exp_ret = None
        conf_label = None
        conf_score = None
        predicted_price = None
        exp_vol = None
        try:
            if isinstance(forecast, dict):
                exp_ret = forecast.get("expected_return")
                exp_vol = forecast.get("expected_volatility")
                conf_score = (forecast.get("confidence") or {}).get("score")
                conf_label = (forecast.get("confidence") or {}).get("label")
            if isinstance(forecast, dict) and isinstance(quote, dict):
                px = quote.get("price")
                if isinstance(exp_ret, (int, float)) and isinstance(px, (int, float)):
                    predicted_price = round(float(px) * (1.0 + float(exp_ret)), 2)
        except Exception:
            predicted_price = None

        risk_level = _volatility_to_risk_level(exp_vol)
        hl = _horizon_label(horizon)
        interpretation = (
            "Short-term model suggests slight downside."
            if isinstance(exp_ret, (int, float)) and exp_ret < 0
            else "Short-term model suggests modest upside potential."
            if isinstance(exp_ret, (int, float)) and exp_ret > 0
            else "Model is close to neutral on short-term direction."
        )
        risk_factors = "Model is based on historical price/volatility patterns only; it does not account for new fundamental information."
        conclusion = "Use this forecast as one input among many; avoid over-sizing positions purely on this signal."

        current_price = (quote or {}).get("price") if isinstance(quote, dict) else None
        metrics = {
            "current_price": current_price,
            "predicted_price": predicted_price,
            "expected_return": exp_ret,
            "expected_volatility": exp_vol,
            "horizon": horizon,
            "horizon_label": hl,
            "risk_level": risk_level,
            "confidence_score": conf_score if isinstance(conf_score, (int, float)) else None,
            "confidence_label": conf_label,
        }

        result = {
            "analysis": "Prediction Summary",
            "metrics": metrics,
            "interpretation": interpretation,
            "risk_factors": risk_factors,
            "conclusion": conclusion,
        }

        message = _format_prediction_message(
            sym, current_price, predicted_price, exp_ret, horizon, conf_label, risk_level, interpretation, risk_factors, conclusion
        )

        return _chat_response(
            {"source": "prediction", "result": result, "query": q},
            {"last_symbol": sym, "last_intent": "prediction"},
        )

    # Investment advice (diversified suggestions)
    if intent == "investment_advice":
        from app.services.advisor_v4.portfolio_optimizer import optimize_portfolio
        from app.services.advisor_v4.risk_engine import summarise_risk
        from app.services.sector_service import SECTOR_STOCKS

        risk_hint = "moderate"
        low = q.lower()
        if "conservative" in low or "low risk" in low:
            risk_hint = "conservative"
        if "aggressive" in low or "high risk" in low:
            risk_hint = "aggressive"

        # Curated diversified basket (existing live symbols)
        basket = [
            SECTOR_STOCKS["banking"][0],
            SECTOR_STOCKS["it"][0],
            SECTOR_STOCKS["fmcg"][0],
            SECTOR_STOCKS["pharma"][0],
            SECTOR_STOCKS["energy"][0],
            SECTOR_STOCKS["auto"][0],
        ]
        opt = await _run_sync_with_timeout(optimize_portfolio, sorted(set(basket)), timeout_s=10.0)
        weights = (opt or {}).get("weights") if isinstance(opt, dict) else None
        risk = await _run_sync_with_timeout(summarise_risk, weights or {}, timeout_s=10.0) if weights else None

        sector_allocation = {
            "banking": 25 if risk_hint != "conservative" else 20,
            "it": 20 if risk_hint != "conservative" else 15,
            "fmcg": 15 if risk_hint == "conservative" else 10,
            "pharma": 15 if risk_hint == "conservative" else 10,
            "energy": 15 if risk_hint == "aggressive" else 10,
            "auto": 10,
        }
        explanation = (
            "This is a diversified example allocation across major Indian sectors. "
            "If you share your risk profile and horizon, I can tailor weights and pick alternatives within each sector."
        )

        return _chat_response(
            {
                "source": "investment_advice",
                "result": {
                    "amount_inr": classified.wants_amount_inr,
                    "risk_profile": risk_hint,
                    "sector_allocation": sector_allocation,
                    "example_stocks": basket,
                    "optimizer": opt,
                    "risk": risk,
                    "explanation": explanation,
                },
                "query": q,
            },
            {"last_intent": "investment_advice"},
        )

    # Portfolio analysis (keyword without pasted weights)
    if intent in {"portfolio_analysis", "portfolio_rebalance"} and last_portfolio_allocs:
        portfolio_result = await _portfolio_allocation_analysis(last_portfolio_allocs)
        return _chat_response({"source": "portfolio_analysis", "result": portfolio_result, "query": q}, {"last_intent": intent})
    if intent in {"portfolio_analysis", "portfolio_rebalance"}:
        return (
            {
                "message": "Paste your portfolio weights like:\nReliance 40%\nTCS 30%\nHDFC Bank 30%\n…and I’ll analyze risk, diversification, and suggest a potential rebalance.",
            },
            {"last_intent": intent},
        )

    # Stock analysis / advisor recommendation / buy decision
    sym = primary_symbol or (ctx.get("last_symbol") if isinstance(ctx.get("last_symbol"), str) else None)
    sym_norm = _normalize_symbol_maybe(sym) if sym else None
    if sym_norm and intent in {"advisor_recommendation", "buy_decision"}:
        from app.services.advisor_v3.reasoning_engine import analyse_symbol_v3
        from app.services.stock_service import get_stock_detail
        from app.services.advisor_v4.regime_detection import detect_market_regime

        v3 = await _run_sync_with_timeout(analyse_symbol_v3, sym_norm, timeout_s=10.0)
        detail = await _run_sync_with_timeout(get_stock_detail, sym_norm, timeout_s=10.0)
        if not isinstance(detail, dict) or detail.get("error"):
            detail = {}

        sector = detail.get("sector") or "N/A"
        pe = detail.get("pe")
        price = detail.get("price")
        # Use the existing sector PE heuristic when available
        try:
            from app.services.query_service import SECTOR_AVG_PE  # type: ignore
            sector_avg_pe = float(SECTOR_AVG_PE.get(sector, SECTOR_AVG_PE.get("N/A", 18)))
        except Exception:
            sector_avg_pe = 18
        interpretation = None
        if isinstance(v3, dict) and v3.get("recommendation"):
            interpretation = v3.get("explanation")

        # Final advisor score combining factors as requested
        fs = (v3 or {}).get("factor_scores") or {}
        pred_f = float(fs.get("prediction", 0.5))
        mom_f = float(fs.get("momentum", 0.5))
        sent_f = float(fs.get("sentiment", 0.5))
        vol_adj_f = float(fs.get("volatility", 0.5))
        final_score_0_1 = max(
            0.0,
            min(
                1.0,
                0.4 * pred_f + 0.3 * mom_f + 0.2 * sent_f + 0.1 * vol_adj_f,
            ),
        )
        final_score_100 = round(final_score_0_1 * 100)
        if final_score_100 >= 60:
            final_rec = "BUY"
        elif final_score_100 <= 40:
            final_rec = "SELL"
        else:
            final_rec = "HOLD"

        interpretation_text = interpretation or "I could not generate a full reasoning trace right now; showing live metrics instead."
        risk_factors_text = "Sector and macro risks apply; use position sizing and risk controls."
        conclusion_text = f"Final Score: {final_score_100}/100 → Recommendation: {final_rec}. Use this as decision support, not financial advice."
        score_components = {
            "prediction": pred_f,
            "momentum": mom_f,
            "sentiment": sent_f,
            "volatility_adjustment": vol_adj_f,
        }
        # Fetch current market regime for context in buy decisions
        regime = await _run_sync_with_timeout(detect_market_regime, "^NSEI", timeout_s=8.0)
        mr = (regime or {}).get("market_regime") if isinstance(regime, dict) else None
        if mr == "bull_market":
            mr_label = "bullish"
        elif mr == "bear_market":
            mr_label = "bearish"
        elif mr == "sideways_market":
            mr_label = "sideways / range-bound"
        else:
            mr_label = "uncertain"

        result = {
            "analysis": "Advisor Recommendation" if intent == "advisor_recommendation" else "Buy Decision",
            "metrics": {
                "symbol": sym_norm,
                "price": price,
                "pe": pe,
                "sector": sector,
                "sector_avg_pe": sector_avg_pe,
                "final_score": final_score_100,
                "score_components": score_components,
                "market_regime": mr,
            },
            "interpretation": interpretation_text,
            "risk_factors": risk_factors_text,
            "conclusion": conclusion_text,
        }

        if intent == "advisor_recommendation":
            message = _format_advisor_score_message(
                sym_norm, score_components, final_score_100, final_rec, interpretation_text, risk_factors_text, conclusion_text
            )
            return _chat_response(
                {"source": "buy_recommendation", "result": result, "query": q},
                {"last_symbol": sym_norm, "last_intent": "buy_recommendation"},
            )

        # buy_decision: more explicit decision-style formatting
        clean_sym = str(sym_norm).replace(".NS", "").replace(".BO", "")
        lines = [
            f"Buy Decision – {clean_sym}",
            "",
            "Valuation / Fundamentals:",
        ]
        val_note = f"P/E {pe} vs sector avg ~{sector_avg_pe:.1f}" if pe is not None else f"P/E data unavailable; sector avg ~{sector_avg_pe:.1f}"
        lines.append(f"- Sector: {sector}")
        lines.append(f"- {val_note}")
        lines.append("")
        lines.append("Momentum:")
        lines.append(f"- Momentum factor score: {int(round(mom_f * 100))}/100 (higher implies stronger recent trend)")
        lines.append("")
        lines.append("AI Prediction:")
        lines.append(f"- Prediction factor score: {int(round(pred_f * 100))}/100")
        lines.append("")
        lines.append("Market Regime:")
        lines.append(f"- Current regime for NIFTY: {mr_label}")
        lines.append("")
        lines.append("Conclusion:")
        lines.append(f"- Overall: {final_rec} — {interpretation_text}")
        lines.append(f"- {risk_factors_text}")
        lines.append("Use this as structured decision support, not a guarantee or personalised financial advice.")

        message = "\n".join(lines)
        return _chat_response(
            {"source": "buy_recommendation", "result": result, "message": message, "query": q},
            {"last_symbol": sym_norm, "last_intent": "buy_decision"},
        )

    if sym_norm and intent in {"stock_analysis"}:
        # "tell me about HDFC bank" style
        from app.services.stock_service import get_stock_detail

        detail = await _run_sync_with_timeout(get_stock_detail, sym_norm, timeout_s=10.0)
        if isinstance(detail, dict) and not detail.get("error"):
            name = str(detail.get("symbol") or sym_norm).replace(".NS", "").replace(".BO", "")
            sector = detail.get("sector") or "N/A"
            pe = detail.get("pe")
            try:
                from app.services.query_service import SECTOR_AVG_PE  # type: ignore
                sector_avg_pe = float(SECTOR_AVG_PE.get(sector, SECTOR_AVG_PE.get("N/A", 18)))
            except Exception:
                sector_avg_pe = 18
            interp = ""
            if pe is not None:
                if pe < sector_avg_pe:
                    interp = f"{name} looks cheaper than the rough sector average PE (~{sector_avg_pe}), but confirm growth/quality drivers."
                else:
                    interp = f"Valuation is around PE {pe} vs rough sector average ~{sector_avg_pe}; a moderate premium may be justified by growth."
            risk_factors_stock = "Sector and market risks apply; do your own research."
            result_stock = {
                "title": f"Stock Analysis: {name}",
                "symbol": detail.get("symbol") or sym_norm,
                "price": detail.get("price"),
                "pe": pe,
                "dividendYield": detail.get("dividendYield", 0),
                "marketCap": detail.get("marketCap"),
                "sector": sector,
                "sector_avg_pe": sector_avg_pe,
                "interpretation": interp,
                "risk_factors": risk_factors_stock,
            }
            message_stock = _format_stock_analysis_message(result_stock, interp, risk_factors_stock)
            return _chat_response(
                {"source": "stock_analysis", "result": result_stock, "query": q},
                {"last_symbol": detail.get("symbol") or sym_norm, "last_intent": "stock_analysis"},
            )

    # Legacy momentum/trend shortcut (kept only for explicit top gainers/losers intent)
    if any(x in q.lower() for x in ("top gainers", "top losers")):
        from app.services.stock_service import get_top_gainers_losers

        r = await _run_sync_with_timeout(get_top_gainers_losers, 5, timeout_s=10.0)
        if r:
            return _chat_response({"source": "market_trend", "result": r, "query": q}, {"last_intent": "market_trend"})

    # Reduced fallback: only when no intent matched and no finance keyword do we show generic help.
    if has_finance_signal(q) or primary_symbol:
        if not primary_symbol and intent in {"advisor_recommendation", "buy_decision", "technical_indicator", "prediction", "stock_analysis"}:
            return ({"message": "Which stock symbol/company should I use? Example: Should I buy RELIANCE?"}, {})
        return ({"message": "Can you clarify: price/RSI/MACD, comparison, prediction, portfolio risk, or market regime?"}, {})

    return (
        {"message": "I can help with stock analysis, RSI/MACD, comparisons, portfolio risk, market news, or macro data. What would you like to know?"},
        {"last_intent": "fallback"},
    )

