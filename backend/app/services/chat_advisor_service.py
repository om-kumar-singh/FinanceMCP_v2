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
from app.services.chat_intent_classifier import classify_intent, get_raw_parser_symbols, has_finance_signal, is_hypothetical_macro_query
from app.utils.yfinance_wrapper import fetch_history, fetch_info
from app.services.mock_data import sample_mock_news
from app.services.news_service import get_market_news
from app.services.stock_search_service import resolve_symbol
from app.services.advisor_v5.response_generator import (
    _SOURCES_WITHOUT_FRONTEND_HANDLER,
    build_chat_response,
    format_advisor_output,
)

logger = logging.getLogger(__name__)


COMMODITY_MAP: Dict[str, str] = {
    "crude oil": "CL=F",
    "natural gas": "NG=F",
    "crude": "CL=F",
    "oil": "CL=F",
    "wti": "CL=F",
    "brent": "BZ=F",
    "gold": "GC=F",
    "silver": "SI=F",
    "copper": "HG=F",
    "platinum": "PL=F",
    "aluminium": "ALI=F",
    "aluminum": "ALI=F",
    "wheat": "ZW=F",
    "corn": "ZC=F",
    "bitcoin": "BTC-USD",
    "btc": "BTC-USD",
    "ethereum": "ETH-USD",
    "eth": "ETH-USD",
}

_COMMODITY_TICKERS = set(COMMODITY_MAP.values())


_COMMON_COMPARE_ALIASES: Dict[str, str] = {
    "tcs": "TCS.NS",
    "reliance": "RELIANCE.NS",
    "infy": "INFY.NS",
    "infosys": "INFY.NS",
    "hdfc": "HDFCBANK.NS",
    "hdfcbank": "HDFCBANK.NS",
    "wipro": "WIPRO.NS",
    "hcl": "HCLTECH.NS",
    "hcltech": "HCLTECH.NS",
    "icici": "ICICIBANK.NS",
    "icicibank": "ICICIBANK.NS",
    "sbi": "SBIN.NS",
    "bajaj": "BAJFINANCE.NS",
    "bajajfinance": "BAJFINANCE.NS",
    "axis": "AXISBANK.NS",
    "axisbank": "AXISBANK.NS",
    "kotak": "KOTAKBANK.NS",
    "ongc": "ONGC.NS",
    "tatamotors": "TATAMOTORS.NS",
    "tata": "TATAMOTORS.NS",
    "maruti": "MARUTI.NS",
    "adani": "ADANIENT.NS",
    "sunpharma": "SUNPHARMA.NS",
    "sun": "SUNPHARMA.NS",
    "ltim": "LTIM.NS",
    "ltimindtree": "LTIM.NS",
    "nifty": "^NSEI",
    "sensex": "^BSESN",
}

_COMPARE_STOPWORDS = {
    "compare",
    "vs",
    "versus",
    "vc",
    "v/s",
    "v",
    "vd",
    "and",
    "with",
    "between",
    "or",
    "please",
    "me",
    "the",
    "stocks",
    "stock",
}


def get_stock_metrics(ticker_symbol):
    try:
        # --- HISTORY (most reliable source) ---
        # Call history BEFORE info to avoid session issues
        try:
            hist = fetch_history(ticker_symbol, period="1y", ttl=60)
        except Exception:
            hist = None

        price = None
        today_change = "N/A"
        today_change_float = None
        fifty_two_high = "N/A"
        fifty_two_low = "N/A"
        fifty_two_high_val = None
        fifty_two_low_val = None

        if hist is not None and not hist.empty:
            # Price — from last close
            price = round(float(hist["Close"].iloc[-1]), 2)

            # Today change — last 2 closing prices
            if len(hist) >= 2:
                prev = float(hist["Close"].iloc[-2])
                curr = float(hist["Close"].iloc[-1])
                chg = ((curr - prev) / prev) * 100
                today_change = f"+{chg:.2f}%" if chg >= 0 else f"{chg:.2f}%"
                today_change_float = chg

            # 52W High/Low from 1y history
            try:
                if len(hist) > 5:
                    high_val = round(float(hist["High"].max()), 2)
                    low_val = round(float(hist["Low"].min()), 2)
                    fifty_two_high_val = high_val
                    fifty_two_low_val = low_val
                    fifty_two_high = f"Rs.{high_val:,.2f}"
                    fifty_two_low = f"Rs.{low_val:,.2f}"
                else:
                    fifty_two_high = "N/A"
                    fifty_two_low = "N/A"
            except Exception:
                fifty_two_high = "N/A"
                fifty_two_low = "N/A"

        # Fallback price if history failed
        if price is None:
            price = 0.0

        # --- INFO DICT (only for metadata) ---
        info = fetch_info(ticker_symbol, ttl=300)

        # P/E Ratio
        pe = info.get("trailingPE") or info.get("forwardPE")
        pe = round(float(pe), 1) if pe else "N/A"

        # Dividend Yield — robust handling of decimal vs percent
        raw_yield = info.get("dividendYield")
        if raw_yield:
            raw_yield = float(raw_yield)
            # yfinance for .NS stocks always returns as decimal
            # e.g. 0.0249 means 2.49%, 0.39 means 39% which is wrong
            # Safe rule: if value > 0.25, it is already a percentage
            if raw_yield > 0.25:
                div_yield_float = round(raw_yield, 2)
            else:
                div_yield_float = round(raw_yield * 100, 2)
            div_yield = f"{div_yield_float}%"
        else:
            div_yield = "0.00%"
            div_yield_float = 0.0

        # Market Cap — convert from raw rupees to Crores / Lakh Crores
        raw_mkt_cap = info.get("marketCap", 0)
        if raw_mkt_cap:
            raw_mkt_cap = float(raw_mkt_cap)
            crore_value = raw_mkt_cap / 10_000_000  # convert to Crores
            if crore_value >= 100_000:  # >= 1 Lakh Crore
                mkt_cap_str = f"{round(crore_value / 100_000, 2)} L Cr"
            else:
                mkt_cap_str = f"{round(crore_value, 2)} Cr"
        else:
            mkt_cap_str = "N/A"
        raw_mkt_cap_float = raw_mkt_cap if raw_mkt_cap else 0

        # Sector
        sector = info.get("sector", "N/A")

        return {
            "price":               f"Rs.{price:,.2f}",
            "price_float":         price,
            "pe":                  pe,
            "pe_float":            float(pe) if pe != "N/A" else 9999,
            "div_yield":           div_yield,
            "div_yield_float":     div_yield_float,
            "market_cap":          mkt_cap_str,
            "market_cap_float":    raw_mkt_cap_float,
            "fifty_two_high":      fifty_two_high_val if fifty_two_high_val is not None else None,
            "fifty_two_low":       fifty_two_low_val if fifty_two_low_val is not None else None,
            "sector":              sector,
            "today_change":        today_change,
            "today_change_float":  today_change_float,
        }
    except Exception as e:
        print(f"Error fetching {ticker_symbol}: {e}")
        return None


def get_stock_metrics_safe(ticker_symbol):
    try:
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(get_stock_metrics, ticker_symbol)
            return future.result(timeout=8)  # 8 second max per stock
    except Exception as e:
        print(f"Timeout or error fetching {ticker_symbol}: {e}")
        return None


def _extract_comparison_symbols_from_query(q: str, *, limit: int = 6) -> List[str]:
    """
    Extract comparison symbols from free text using a simple token-based parser:

    1) Strip common connective words (compare, vs, and, with, between, or, please, me, the, stocks, stock)
    2) Split by spaces/commas
    3) Map tokens via COMMON_COMPARE_ALIASES first
    4) Fallback to _normalize_symbol_maybe (yfinance-backed resolution) for remaining tokens
    5) Deduplicate while preserving order; cap at `limit`
    """
    if not q:
        return []

    raw = (q or "").lower()
    # First, resolve explicit commodity keywords/phrases so they never fall through to stock lookup.
    commodity_symbols: List[str] = []
    seen_symbols: set[str] = set()
    raw_with_spaces = f" {raw} "
    for name, ticker in COMMODITY_MAP.items():
        needle = f" {name} "
        if needle in raw_with_spaces and ticker not in seen_symbols:
            commodity_symbols.append(ticker)
            seen_symbols.add(ticker)
            raw_with_spaces = raw_with_spaces.replace(needle, " ")
    raw = raw_with_spaces.strip()
    # Normalize some vs variants
    raw = raw.replace("v/s", "vs").replace("v s", "vs").replace("vs.", "vs").replace("vc", "vs").replace("vd", "vs")

    for w in _COMPARE_STOPWORDS:
        raw = raw.replace(f" {w} ", " ")
        if raw.startswith(w + " "):
            raw = raw[len(w) + 1 :]
        raw = raw.replace(" " + w + ",", " ")
        raw = raw.replace("," + w + " ", " ")

    tokens: List[str] = []
    for part in raw.replace(",", " ").split():
        t = part.strip().lower()
        if not t or t in _COMPARE_STOPWORDS:
            continue
        tokens.append(t)

    symbols: List[str] = []
    seen: set[str] = set()

    # 1) Alias dictionary
    for tok in tokens:
        mapped = _COMMON_COMPARE_ALIASES.get(tok)
        if mapped and mapped not in seen:
            symbols.append(mapped)
            seen.add(mapped)
            if len(commodity_symbols) + len(symbols) >= limit:
                return commodity_symbols + symbols

    # 2) Fallback: use existing symbol normalizer (yfinance-backed via resolve_symbol)
    for tok in tokens:
        mapped = _normalize_symbol_maybe(tok)
        if mapped and mapped not in seen:
            symbols.append(mapped)
            seen.add(mapped)
            if len(commodity_symbols) + len(symbols) >= limit:
                break

    return commodity_symbols + symbols

_COMMON_COMPARE_ALIASES: Dict[str, str] = {
    "tcs": "TCS.NS",
    "reliance": "RELIANCE.NS",
    "infy": "INFY.NS",
    "infosys": "INFY.NS",
    "hdfc": "HDFCBANK.NS",
    "hdfcbank": "HDFCBANK.NS",
    "wipro": "WIPRO.NS",
    "hcl": "HCLTECH.NS",
    "hcltech": "HCLTECH.NS",
    "icici": "ICICIBANK.NS",
    "icicibank": "ICICIBANK.NS",
    "sbi": "SBIN.NS",
    "bajaj": "BAJFINANCE.NS",
    "bajajfinance": "BAJFINANCE.NS",
    "axis": "AXISBANK.NS",
    "axisbank": "AXISBANK.NS",
    "kotak": "KOTAKBANK.NS",
    "ongc": "ONGC.NS",
    "tatamotors": "TATAMOTORS.NS",
    "tata": "TATAMOTORS.NS",
    "maruti": "MARUTI.NS",
    "adani": "ADANIENT.NS",
    "sunpharma": "SUNPHARMA.NS",
    "sun": "SUNPHARMA.NS",
    "ltim": "LTIM.NS",
    "ltimindtree": "LTIM.NS",
    "nifty": "^NSEI",
    "sensex": "^BSESN",
}

_COMPARE_STOPWORDS = {
    "compare",
    "vs",
    "versus",
    "and",
    "with",
    "between",
    "or",
    "please",
    "me",
    "the",
    "stocks",
    "stock",
}


def _extract_comparison_symbols_from_query(q: str, *, limit: int = 6) -> List[str]:
    """
    Extract comparison symbols from free text using a simple token-based parser:

    1) Strip common connective words (compare, vs, and, with, between, or, please, me, the, stocks, stock)
    2) Split by spaces/commas
    3) Map tokens via COMMON_COMPARE_ALIASES first
    4) Fallback to _normalize_symbol_maybe (yfinance-backed resolution) for remaining tokens
    5) Deduplicate while preserving order; cap at `limit`
    """
    if not q:
        return []

    raw = (q or "").lower()
    for w in _COMPARE_STOPWORDS:
        raw = raw.replace(f" {w} ", " ")
        if raw.startswith(w + " "):
            raw = raw[len(w) + 1 :]
        raw = raw.replace(" " + w + ",", " ")
        raw = raw.replace("," + w + " ", " ")

    tokens: List[str] = []
    for part in raw.replace(",", " ").split():
        t = part.strip().lower()
        if not t or t in _COMPARE_STOPWORDS:
            continue
        tokens.append(t)

    symbols: List[str] = []
    seen: set[str] = set()

    # 1) Alias dictionary
    for tok in tokens:
        mapped = _COMMON_COMPARE_ALIASES.get(tok)
        if mapped and mapped not in seen:
            symbols.append(mapped)
            seen.add(mapped)
            if len(symbols) >= limit:
                return symbols

    # 2) Fallback: use existing symbol normalizer (yfinance-backed via resolve_symbol)
    for tok in tokens:
        mapped = _normalize_symbol_maybe(tok)
        if mapped and mapped not in seen:
            symbols.append(mapped)
            seen.add(mapped)
            if len(symbols) >= limit:
                break

    return symbols


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


# Direction-aware impact text: (up_text, down_text)
_MACRO_IMPACT_BY_DIRECTION: Dict[str, Tuple[str, str]] = {
    "us_10y_yield": (
        "Bond yield rose today. This tightens global liquidity and increases the discount rate on future earnings. IT and growth stocks face valuation pressure. Real estate and capital-heavy sectors also affected. Defensive sectors less impacted.",
        "Bond yield fell today. This eases global liquidity conditions. Growth stocks like IT get relief as discount rates fall. Generally positive for equity valuations broadly.",
    ),
    "wti_crude": (
        "Aviation, logistics, paints, and petrochemical sectors face margin pressure. ONGC and oil producers benefit. Inflation risk increases for India as a major oil importer.",
        "Aviation and logistics get cost relief. India's trade deficit narrows. Inflation pressure eases. Negative for ONGC and oil producers.",
    ),
    "usd_inr": (
        "IT exporters (TCS, INFY, WIPRO) and pharma exporters (Sun Pharma, Dr Reddy) benefit directly. Oil import costs rise. Airlines and importers face higher costs.",
        "IT and pharma export revenues reduced in INR terms. Import costs ease. Oil companies benefit from lower input costs.",
    ),
    "gold": (
        "Risk-off sentiment detected. Investors moving to safe havens. Broad equity markets may face selling pressure. FMCG and pharma as defensive plays preferred over cyclicals.",
        "Risk appetite returning. Investors moving back to equities. Positive signal for broader market sentiment.",
    ),
    "india_vix": (
        "Market fear rising. Short-term volatility expected. Reduce position sizes, tighten stop-losses. Avoid leveraged positions.",
        "Market fear reducing. Stable conditions returning. Favorable for building equity positions gradually.",
    ),
}

_MACRO_WHAT_MEANS_BY_DIRECTION: Dict[str, Tuple[str, str]] = {
    "us_10y_yield": (
        "Bond yield rose {cp:.2f}% to {cv:.2f} today. This tightens global liquidity and increases the discount rate on future earnings.",
        "Bond yield fell {cp:.2f}% to {cv:.2f} today. This eases global liquidity conditions.",
    ),
    "wti_crude": (
        "Crude oil rose {cp:.2f}% to {cv:.2f} today. India imports ~85% of its oil needs.",
        "Crude oil fell {cp:.2f}% to {cv:.2f} today. Eases input cost pressure for oil-dependent sectors.",
    ),
    "usd_inr": (
        "USD/INR rose {cp:.2f}% to {cv:.2f} — INR weakening. A higher value means more rupees per dollar.",
        "USD/INR fell {cp:.2f}% to {cv:.2f} — INR strengthening. Import costs ease.",
    ),
    "gold": (
        "Gold rose {cp:.2f}% to {cv:.2f} today. Gold is a global safe-haven asset.",
        "Gold fell {cp:.2f}% to {cv:.2f} today. Suggests risk-on sentiment returning.",
    ),
    "india_vix": (
        "India VIX rose {cp:.2f}% to {cv:.2f} today. Market fear has elevated. A VIX above 20 signals elevated volatility.",
        "India VIX fell {cp:.2f}% to {cv:.2f} today. Market fear has reduced. A VIX below 20 is generally considered a calm zone.",
    ),
}

_MACRO_LABELS: Dict[str, str] = {
    "us_10y_yield": "US 10Y Bond Yield",
    "wti_crude": "Crude Oil (WTI)",
    "usd_inr": "USD/INR",
    "gold": "Gold",
    "india_vix": "India VIX",
}


HYPOTHETICAL_MACRO_KEYWORDS = ("if ", "when ", "suppose ", "assuming ", "what if ", "hypothetically", "in case ")


def _is_hypothetical_macro_question(query: str) -> bool:
    """Detect hypothetical macro questions (answer scenario, not current direction)."""
    q = (query or "").lower()
    return any(kw in q for kw in HYPOTHETICAL_MACRO_KEYWORDS)


def _detect_hypothetical_scenario(query: str) -> Optional[Tuple[str, str]]:
    """Detect (signal_key, direction) for hypothetical. direction: 'up' or 'down'."""
    q = (query or "").lower()
    if re.search(r"\b(bond|yield|10y|treasury)\b.*\b(ris(e|ing)|up|spike)\b", q) or re.search(r"\b(ris(e|ing)|up|spike)\b.*\b(bond|yield)\b", q):
        return ("us_10y_yield", "up")
    if re.search(r"\b(bond|yield)\b.*\b(fall|down|drop)\b", q) or re.search(r"\b(fall|down|drop)\b.*\b(bond|yield)\b", q):
        return ("us_10y_yield", "down")
    if re.search(r"\b(crude|oil)\b.*\b(ris(e|ing)|up|spike)\b", q) or re.search(r"\b(ris(e|ing)|up|spike)\b.*\b(crude|oil)\b", q):
        return ("wti_crude", "up")
    if re.search(r"\b(crude|oil)\b.*\b(fall|down|drop)\b", q):
        return ("wti_crude", "down")
    if re.search(r"\b(inr|rupee)\b.*\b(weak|weaken|fall|down)\b", q) or re.search(r"\b(usd|dollar)\b.*\b(ris(e|ing)|up)\b", q):
        return ("usd_inr", "up")
    if re.search(r"\b(inr|rupee)\b.*\b(strengthen|rise|up)\b", q):
        return ("usd_inr", "down")
    if re.search(r"\b(vix|volatility)\b.*\b(ris(e|ing)|up|spike)\b", q):
        return ("india_vix", "up")
    if re.search(r"\b(vix|volatility)\b.*\b(fall|down)\b", q):
        return ("india_vix", "down")
    if re.search(r"\b(gold)\b.*\b(ris(e|ing)|up|rally)\b", q):
        return ("gold", "up")
    if re.search(r"\b(gold)\b.*\b(fall|down)\b", q):
        return ("gold", "down")
    return None


# Hypothetical scenario content: (sectors_avoid, sectors_benefit, stocks_avoid, stocks_prefer)
_HYPOTHETICAL_SCENARIO_CONTENT: Dict[str, Dict[str, Tuple[List[str], List[str], List[str], List[str]]]] = {
    "us_10y_yield": {
        "up": (
            ["IT / Technology — growth stock valuations compress", "Real Estate — higher borrowing costs hurt demand", "Capital Goods — financing costs increase", "NBFCs — cost of funds rises"],
            ["Banking (PSU) — NIM expansion on lending rates", "Insurance — higher reinvestment yields"],
            ["TCS", "INFY", "L&T", "Bajaj Finance"],
            ["SBI", "Bank of Baroda", "LIC"],
        ),
        "down": (
            ["Banking — NIM pressure", "Insurance — lower reinvestment yields"],
            ["IT / Technology — discount rates fall", "Real Estate — borrowing cost relief", "Growth stocks"],
            ["SBI", "Bank of Baroda"],
            ["TCS", "INFY", "L&T"],
        ),
    },
    "wti_crude": {
        "up": (
            ["Aviation — fuel costs spike", "Logistics — margin pressure", "Paints — raw material costs", "Petrochemicals"],
            ["ONGC", "Oil India", "OIL — upstream producers benefit"],
            ["IndiGo", "SpiceJet", "Asian Paints"],
            ["ONGC", "Oil India"],
        ),
        "down": (
            ["ONGC", "Oil producers — price decline"],
            ["Aviation", "Logistics", "Paints — cost relief", "India trade deficit narrows"],
            ["ONGC", "Oil India"],
            ["IndiGo", "Asian Paints", "Delhivery"],
        ),
    },
    "usd_inr": {
        "up": (
            ["Oil importers", "Airlines — USD costs", "Capital goods importers"],
            ["IT exporters (TCS, INFY, WIPRO)", "Pharma exporters (Sun Pharma, Dr Reddy)"],
            ["Bharat Petroleum", "IndiGo"],
            ["TCS", "INFY", "Sun Pharma", "Dr Reddy"],
        ),
        "down": (
            ["IT exporters", "Pharma exporters — INR revenue hit"],
            ["Oil companies", "Importers", "Airlines"],
            ["TCS", "INFY", "WIPRO"],
            ["BPCL", "HPCL", "IndiGo"],
        ),
    },
    "india_vix": {
        "up": (
            ["All sectors — broad selling pressure", "Avoid leveraged positions", "Reduce position sizes"],
            [],
            ["All stocks — tighten stop-losses"],
            [],
        ),
        "down": (
            [],
            ["All sectors — stable conditions", "Favorable for building positions gradually"],
            [],
            ["Quality large-caps", "Index funds"],
        ),
    },
    "gold": {
        "up": (
            ["Cyclicals", "Growth stocks", "IT — risk-off rotation"],
            ["FMCG", "Pharma — defensive plays", "Banking"],
            ["TCS", "INFY", "L&T"],
            ["HUL", "ITC", "Sun Pharma", "SBI"],
        ),
        "down": (
            ["Defensives may lag"],
            ["Cyclicals", "IT", "Growth stocks — risk-on"],
            [],
            ["TCS", "INFY", "L&T"],
        ),
    },
}


def _format_hypothetical_macro_analysis(
    signals: Dict[str, Any],
    query: str,
    scenario: Tuple[str, str],
    data_timestamp: str,
) -> str:
    """Format hypothetical macro scenario (answer the scenario, not current direction)."""
    signal_key, direction = scenario
    label = _MACRO_LABELS.get(signal_key, signal_key)
    dir_word = "RISING" if direction == "up" else "FALLING"
    scenario_title = f"{dir_word} {label.upper().replace(' (WTI)', '')} SCENARIO"

    s = signals.get(signal_key) if isinstance(signals, dict) else None
    cv_str = "N/A"
    cp_str = ""
    if s and isinstance(s, dict):
        cv = s.get("current_value")
        cp = s.get("change_pct")
        try:
            cv = float(cv) if cv is not None else None
            cp = float(cp) if cp is not None else None
        except Exception:
            cv, cp = None, None
        if cv is not None:
            cv_str = f"{cv:.2f}"
        if cp is not None:
            cp_str = f" ({cp:+.2f}% today)"

    content = _HYPOTHETICAL_SCENARIO_CONTENT.get(signal_key, {}).get(direction)
    avoid, benefit, stocks_avoid, stocks_prefer = ([], [], [], []) if not content else content

    lines = [
        f"**MACRO SIGNAL ANALYSIS — {scenario_title}**",
        "",
        f"**Current Live Value:** {cv_str}{cp_str}",
        "",
        f"**Your Question:** {query.strip()}",
        "",
        "**Sectors to AVOID when {} {}:**".format(label.split("(")[0].strip().lower(), "rises" if direction == "up" else "falls"),
    ]
    for item in avoid:
        lines.append(f"• {item}")
    if benefit:
        lines.extend(["", "**Sectors that BENEFIT when {} {}:**".format(label.split("(")[0].strip().lower(), "rises" if direction == "up" else "falls")])
        for item in benefit:
            lines.append(f"• {item}")
    if stocks_avoid or stocks_prefer:
        lines.append("")
        if stocks_avoid:
            lines.append("**Stocks to watch:**")
            lines.append(f"• Avoid: {', '.join(stocks_avoid)}")
        if stocks_prefer:
            lines.append(f"• Prefer: {', '.join(stocks_prefer)}")
    lines.extend(["", f"**Data as of:** {data_timestamp}"])
    return "\n".join(lines)


def _detect_primary_macro_signal(query: str) -> str:
    """Detect which macro signal the user is asking about. Returns signal key or first available."""
    q = (query or "").lower()
    if re.search(r"\b(vix|volatility)\b", q):
        return "india_vix"
    if re.search(r"\b(bond|yield|10y|10-y|treasury)\b", q):
        return "us_10y_yield"
    if re.search(r"\b(gold)\b", q):
        return "gold"
    if re.search(r"\b(crude|oil|wti|brent)\b", q):
        return "wti_crude"
    if re.search(r"\b(usd|inr|rupee|currency|forex)\b", q):
        return "usd_inr"
    return "india_vix"  # default to VIX for generic macro


def _detect_target_sector(query: str) -> Optional[str]:
    """Detect target sector from query for sector-specific impact."""
    q = (query or "").lower()
    if re.search(r"\baviation\b", q):
        return "aviation"
    if re.search(r"\b(it|technology|tech)\b", q):
        return "IT"
    if re.search(r"\b(banking|banks|financial)\b", q):
        return "Banking"
    if re.search(r"\b(energy|oil)\b", q):
        return "Energy"
    if re.search(r"\bpharma\b", q):
        return "Pharma"
    if re.search(r"\bfmcg\b", q):
        return "FMCG"
    return None


def _format_macro_signal_analysis(
    signals: Dict[str, Any],
    causal_insights: List[Dict[str, Any]],
    data_timestamp: str,
    query: str,
) -> str:
    """Build the standard macro signal analysis format (direction-aware)."""
    primary_key = _detect_primary_macro_signal(query)
    label = _MACRO_LABELS.get(primary_key, "Macro Signal")
    target_sector = _detect_target_sector(query)

    s = signals.get(primary_key) if isinstance(signals, dict) else None
    if not s or not isinstance(s, dict):
        cv, cp, direction = None, None, "flat"
    else:
        cv = s.get("current_value")
        cp = s.get("change_pct")
        direction = s.get("direction") or "flat"
        try:
            cv = float(cv) if cv is not None else None
            cp = float(cp) if cp is not None else None
        except Exception:
            cv, cp = None, None

    lines = [
        "**MACRO SIGNAL ANALYSIS**",
        "",
        f"**Signal:** {label}",
        f"**Current Value:** {f'{cv:.2f}' if cv is not None else 'Unavailable'}",
        f"**Today Change:** {f'{cp:+.2f}%' if cp is not None else 'N/A'} ({direction})",
        "",
        "**What This Means:**",
    ]

    if cv is not None and cp is not None:
        what_tpls = _MACRO_WHAT_MEANS_BY_DIRECTION.get(primary_key)
        if what_tpls:
            up_tpl, down_tpl = what_tpls
            tpl = up_tpl if cp > 0 else down_tpl
            lines.append(tpl.format(cv=cv, cp=abs(cp)))
        else:
            lines.append(f"{label} is at {cv:.2f}, {'up' if cp > 0 else 'down'} {abs(cp):.2f}% today.")
    else:
        lines.append(f"Live data for {label} is temporarily unavailable. Please try again shortly.")

    # Direction-aware impact
    impact_tpls = _MACRO_IMPACT_BY_DIRECTION.get(primary_key)
    impact_text = "Various sectors affected."
    if impact_tpls:
        impact_text = impact_tpls[0] if (cp is not None and cp > 0) else impact_tpls[1]
    lines.extend(["", "**Impact on Indian Markets:**", impact_text])
    if target_sector and target_sector.lower() == "aviation" and primary_key == "wti_crude":
        lines.append("")
        lines.append("For aviation specifically: Rising oil directly increases fuel costs and squeezes margins. Airlines face significant cost pressure when crude spikes.")

    # Current Context: connect to other live signals
    other_parts = []
    for k, v in (signals or {}).items():
        if k == primary_key or not isinstance(v, dict):
            continue
        cv2 = v.get("current_value")
        cp2 = v.get("change_pct")
        name = _MACRO_LABELS.get(k, k)
        if cv2 is not None and cp2 is not None:
            dir2 = "up" if float(cp2) > 0 else "down"
            other_parts.append(f"{name} {dir2} {abs(float(cp2)):.2f}%")
    if other_parts:
        lines.extend(["", "**Current Context:**", f"Combined with {', '.join(other_parts[:3])}, markets are sending mixed signals. Exercise moderate caution."])
    else:
        lines.extend(["", "**Current Context:**", "Other macro signals are unavailable. Treat this as a snapshot, not timing advice."])

    lines.extend(["", f"**Data as of:** {data_timestamp}"])
    return "\n".join(lines)


# Sector → (high_relevance_signals, low_relevance_signals)
_SECTOR_SIGNAL_RELEVANCE: Dict[str, Tuple[List[str], List[str]]] = {
    "IT": (["us_10y_yield", "usd_inr", "india_vix"], ["wti_crude", "gold"]),
    "Banking": (["us_10y_yield", "india_vix", "usd_inr"], ["wti_crude", "gold"]),
    "Energy": (["wti_crude", "usd_inr"], ["gold", "us_10y_yield"]),
    "aviation": (["wti_crude", "usd_inr", "india_vix"], ["gold", "us_10y_yield"]),
    "Pharma": (["usd_inr", "us_10y_yield"], ["wti_crude", "gold"]),
    "FMCG": (["wti_crude"], ["india_vix", "gold"]),
}


def _detect_sector_macro_query(query: str) -> Optional[str]:
    """Detect if query asks to connect macro to a sector."""
    q = (query or "").lower()
    if not re.search(r"\b(connect macro|macro (for|to|signals? for)|macro signals? (for|to))\b", q):
        return None
    for sector in ["IT", "Banking", "Energy", "aviation", "Pharma", "FMCG"]:
        if sector.lower() in q or (sector == "IT" and re.search(r"\bit\b", q)):
            return sector
    return None


def _format_sector_macro_analysis(
    signals: Dict[str, Any],
    sector: str,
    data_timestamp: str,
) -> str:
    """Build sector-specific macro analysis."""
    rel = _SECTOR_SIGNAL_RELEVANCE.get(sector, (["us_10y_yield", "usd_inr", "india_vix"], ["wti_crude", "gold"]))
    high_sigs, low_sigs = rel

    def _fmt_signal(key: str, impact: str) -> str:
        s = signals.get(key) if isinstance(signals, dict) else None
        if not s or not isinstance(s, dict):
            return f"• {_MACRO_LABELS.get(key, key)}: N/A"
        cv = s.get("current_value")
        cp = s.get("change_pct")
        try:
            cv = float(cv) if cv is not None else None
            cp = float(cp) if cp is not None else None
        except Exception:
            cv, cp = None, None
        val = f"{cv:.2f}" if cv is not None else "N/A"
        chg = f"({cp:+.2f}%)" if cp is not None else ""
        return f"• {_MACRO_LABELS.get(key, key)}: {val} {chg} — {impact}"

    sector_display = str(sector).upper()
    lines = [f"**{sector_display} SECTOR — MACRO SIGNAL ANALYSIS**", "", "**Relevant Signals:**"]
    for key in high_sigs:
        impacts = {
            "us_10y_yield": "IT/tech valuations sensitive to discount rates",
            "usd_inr": "Exporters benefit from weaker INR" if sector in ("IT", "Pharma") else "FX impact on sector",
            "india_vix": "Volatility affects liquidity and positioning",
            "wti_crude": "Energy cost pass-through" if sector == "Energy" else "Fuel cost impact on aviation",
        }
        lines.append(_fmt_signal(key, impacts.get(key, "sector impact")))
    lines.extend(["", "**Less Relevant Signals:**"])
    for key in low_sigs:
        imp = "minimal direct sector impact" if key in ("gold", "us_10y_yield") else "indirect risk sentiment"
        lines.append(_fmt_signal(key, imp))
    def _dir(key: str) -> Optional[str]:
        s = signals.get(key) if isinstance(signals, dict) else None
        if not isinstance(s, dict):
            return None
        d = s.get("direction")
        if d in {"up", "down"}:
            return d
        try:
            cp = float(s.get("change_pct"))
            return "up" if cp > 0 else "down" if cp < 0 else "flat"
        except Exception:
            return None

    bullish = 0
    bearish = 0

    # Sector-specific scoring using live directions
    if sector_display == "IT":
        if _dir("us_10y_yield") == "up":
            bearish += 1
        elif _dir("us_10y_yield") == "down":
            bullish += 1
        if _dir("usd_inr") == "up":  # INR weak
            bullish += 1
        elif _dir("usd_inr") == "down":
            bearish += 1
        if _dir("india_vix") == "up":
            bearish += 1
        elif _dir("india_vix") == "down":
            bullish += 1
    elif sector_display == "BANKING":
        if _dir("us_10y_yield") == "up":
            bullish += 1
        elif _dir("us_10y_yield") == "down":
            bearish += 1
        if _dir("india_vix") == "up":
            bearish += 1
        elif _dir("india_vix") == "down":
            bullish += 1
        if _dir("usd_inr") == "up":
            bearish += 1
        elif _dir("usd_inr") == "down":
            bullish += 1
    elif sector_display == "ENERGY":
        if _dir("wti_crude") == "up":
            bullish += 1
        elif _dir("wti_crude") == "down":
            bearish += 1
        if _dir("usd_inr") == "up":
            bullish += 1
        elif _dir("usd_inr") == "down":
            bearish += 1
        if _dir("india_vix") == "up":
            bearish += 1
        elif _dir("india_vix") == "down":
            bullish += 1
    elif sector_display == "PHARMA":
        if _dir("usd_inr") == "up":
            bullish += 1
        elif _dir("usd_inr") == "down":
            bearish += 1
        if _dir("us_10y_yield") == "up":
            bearish += 1
        elif _dir("us_10y_yield") == "down":
            bullish += 1
        if _dir("india_vix") == "up":
            bearish += 1
        elif _dir("india_vix") == "down":
            bullish += 1
    elif sector_display == "FMCG":
        if _dir("wti_crude") == "up":
            bearish += 1
        elif _dir("wti_crude") == "down":
            bullish += 1
        if _dir("india_vix") == "up":
            bearish += 1
        elif _dir("india_vix") == "down":
            bullish += 1
        if _dir("gold") == "up":
            bullish += 1  # defensive tilt helps FMCG
        elif _dir("gold") == "down":
            bearish += 1

    if bullish > bearish:
        overall = "CAUTIOUSLY BULLISH"
    elif bearish > bullish:
        overall = "CAUTIOUSLY BEARISH"
    else:
        overall = "NEUTRAL"

    if sector_display == "IT":
        if overall == "CAUTIOUSLY BULLISH":
            conclusion = (
                "Macro signals are net supportive for IT. Weaker INR boosts export revenues while stable/falling yields reduce valuation pressure. "
                "Recommend selective accumulation in quality IT names on dips."
            )
        elif overall == "CAUTIOUSLY BEARISH":
            conclusion = (
                "Macro headwinds outweigh tailwinds for IT currently. Elevated VIX and yield pressure suggest waiting for better entry points. "
                "Prefer defensive allocation over aggressive IT buying."
            )
        else:
            conclusion = (
                "Macro signals are mixed for IT. No clear directional bias. Focus on stock-specific fundamentals and earnings quality rather than macro timing."
            )
    else:
        # Generic but direction-aware for other sectors
        if overall == "CAUTIOUSLY BULLISH":
            conclusion = "Macro signals are net supportive for this sector. Prefer selective accumulation with staggered entries and normal risk controls."
        elif overall == "CAUTIOUSLY BEARISH":
            conclusion = "Macro headwinds dominate for this sector. Prefer a wait-and-watch stance or smaller position sizes until signals improve."
        else:
            conclusion = "Macro signals are mixed with no strong edge. Prioritize stock-specific fundamentals and risk management."

    lines.extend(
        [
            "",
            f"**Overall {sector_display} Sector Outlook: {overall}**",
            conclusion,
            "",
            f"**Data as of:** {data_timestamp}",
        ]
    )
    return "\n".join(lines)


_EDU_NEUTRAL_MACRO_PHRASES = (
    "what if all signals are neutral",
    "what does neutral mean",
    "what if macro is neutral",
    "all signals neutral",
    "no signals",
    "signals are calm",
)


def _is_neutral_macro_education(query: str) -> bool:
    q = (query or "").lower().strip()
    return any(p in q for p in _EDU_NEUTRAL_MACRO_PHRASES)


def _fmt_live_signal_line(signals: Dict[str, Any], key: str, label: str) -> str:
    s = signals.get(key) if isinstance(signals, dict) else None
    if not isinstance(s, dict):
        return f"• {label:<10}: N/A"
    try:
        cv = float(s.get("current_value")) if s.get("current_value") is not None else None
        cp = float(s.get("change_pct")) if s.get("change_pct") is not None else None
    except Exception:
        cv, cp = None, None
    val = f"{cv:.2f}" if cv is not None else "N/A"
    chg = f"({cp:+.2f}%)" if cp is not None else ""
    return f"• {label:<10}: {val} {chg}".rstrip()


def _format_neutral_macro_scenario(signals: Dict[str, Any], data_timestamp: str) -> str:
    lines = [
        "**MACRO SCENARIO: ALL SIGNALS NEUTRAL**",
        "",
        "**What \"Neutral Macro\" Means:**",
        "When all macro signals are near their baseline with minimal movement, it signals a low-volatility, range-bound market environment. "
        "No strong directional catalyst is present from the macro side.",
        "",
        "**Current Live Signals for Reference:**",
        _fmt_live_signal_line(signals, "us_10y_yield", "Bond Yield"),
        _fmt_live_signal_line(signals, "wti_crude", "Crude Oil"),
        _fmt_live_signal_line(signals, "usd_inr", "USD/INR"),
        _fmt_live_signal_line(signals, "gold", "Gold"),
        _fmt_live_signal_line(signals, "india_vix", "India VIX"),
        "",
        "**What to Do in a Neutral Macro Environment:**",
        "• Focus shifts from macro timing to stock fundamentals",
        "• Quality earnings, revenue growth, and management matter more than macro positioning",
        "• Neutral macro is generally POSITIVE for equities as it removes uncertainty premium",
        "• Good time for systematic SIP investments",
        "• Sector rotation slows — broad market moves together",
        "",
        "**Sectors that Outperform in Neutral Macro:**",
        "• Quality large-caps across IT, Banking, FMCG",
        "• Dividend-paying stocks benefit from stability",
        "• Mid-caps tend to outperform in low-VIX environments",
        "",
        f"**Data as of:** {data_timestamp}",
    ]
    return "\n".join(lines)


_SECTOR_SAFETY_PHRASES = (
    "safest sectors",
    "which sectors are safe",
    "best sectors right now",
    "sectors to invest in",
    "where to invest now",
    "which sectors to buy",
)


def _is_sector_safety_query(query: str) -> bool:
    q = (query or "").lower()
    return any(p in q for p in _SECTOR_SAFETY_PHRASES)


def _get_sig(signals: Dict[str, Any], key: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    s = signals.get(key) if isinstance(signals, dict) else None
    if not isinstance(s, dict):
        return None, None, None
    try:
        cv = float(s.get("current_value")) if s.get("current_value") is not None else None
        cp = float(s.get("change_pct")) if s.get("change_pct") is not None else None
    except Exception:
        cv, cp = None, None
    d = s.get("direction")
    if d not in {"up", "down"} and cp is not None:
        d = "up" if cp > 0 else "down" if cp < 0 else "flat"
    return cv, cp, d


def _format_sector_safety_ranking(signals: Dict[str, Any], data_timestamp: str) -> str:
    y_cv, y_cp, y_dir = _get_sig(signals, "us_10y_yield")
    c_cv, c_cp, c_dir = _get_sig(signals, "wti_crude")
    fx_cv, fx_cp, fx_dir = _get_sig(signals, "usd_inr")
    g_cv, g_cp, g_dir = _get_sig(signals, "gold")
    v_cv, v_cp, v_dir = _get_sig(signals, "india_vix")

    def _score_sector() -> List[Tuple[str, int, str]]:
        out: List[Tuple[str, int, str]] = []

        # FMCG
        score = 0
        reasons = []
        if v_dir == "up":
            score += 1
            reasons.append("defensive demand on risk-off")
        if g_dir == "up":
            score += 1
            reasons.append("risk-off support")
        if c_dir == "up":
            score -= 1
            reasons.append("input cost pressure")
        out.append(("FMCG", score, " + ".join(reasons) if reasons else "stable defensives"))

        # IT
        score = 0
        reasons = []
        if fx_dir == "up":
            score += 1
            reasons.append("INR weak export benefit")
        if y_dir in {"down", "flat"}:
            score += 1
            reasons.append("valuation support")
        if v_dir == "up":
            score -= 1
            reasons.append("growth sell-off risk")
        if y_dir == "up":
            score -= 1
            reasons.append("discount rate pressure")
        out.append(("IT", score, " + ".join(reasons) if reasons else "mixed macro"))

        # Banking
        score = 0
        reasons = []
        if y_dir == "up":
            score += 1
            reasons.append("NIM expansion")
        if v_dir == "down":
            score += 1
            reasons.append("stable credit sentiment")
        if v_dir == "up":
            score -= 1
            reasons.append("risk-off NPA fears")
        out.append(("Banking", score, " + ".join(reasons) if reasons else "mixed yield + VIX"))

        # Energy
        score = 0
        reasons = []
        if c_dir == "up":
            score += 1
            reasons.append("crude revenue positive")
        if c_dir == "down":
            score -= 1
            reasons.append("revenue pressure")
        out.append(("Energy", score, " + ".join(reasons) if reasons else "crude dependent"))

        # Aviation/Logistics
        score = 0
        reasons = []
        if c_dir == "down":
            score += 1
            reasons.append("fuel cost relief")
        if c_dir == "up":
            score -= 1
            reasons.append("fuel cost pressure")
        out.append(("Aviation", score, " + ".join(reasons) if reasons else "fuel sensitive"))

        # Pharma
        score = 0
        reasons = []
        if fx_dir == "up":
            score += 1
            reasons.append("export benefit")
        if v_dir == "up":
            score += 1
            reasons.append("defensive positioning")
        out.append(("Pharma", score, " + ".join(reasons) if reasons else "defensive tilt"))

        return out

    scored = _score_sector()
    scored_sorted = sorted(scored, key=lambda x: (-x[1], x[0]))

    top = [s[0] for s in scored_sorted[:3]]
    bottom = [s[0] for s in scored_sorted[-2:]]

    lines = [
        "**SECTOR SAFETY RANKING — CURRENT MACRO**",
        "",
        "**Live Signals Used:**",
        _fmt_live_signal_line(signals, "us_10y_yield", "Bond Yield"),
        _fmt_live_signal_line(signals, "wti_crude", "Crude Oil"),
        _fmt_live_signal_line(signals, "usd_inr", "USD/INR"),
        _fmt_live_signal_line(signals, "gold", "Gold"),
        _fmt_live_signal_line(signals, "india_vix", "India VIX"),
        "",
        "**Sector Rankings (Safest to Riskiest):**",
        "",
        "| Rank | Sector    | Score | Key Reason |",
        "|------|-----------|-------|------------|",
    ]
    for i, (sec, score, reason) in enumerate(scored_sorted, start=1):
        lines.append(f"| {i} | {sec:<9} | {score:+d} | {reason} |")
    lines.extend(
        [
            "",
            f"**Top Pick Sectors Right Now:** {', '.join(top)}",
            f"**Sectors to Avoid Right Now:** {', '.join(bottom)}",
            "",
            f"**Data as of:** {data_timestamp}",
        ]
    )
    return "\n".join(lines)


def _format_stock_buy_analysis(
    symbol: str,
    decision: str,
    confidence: int,
    price: Any,
    pe: Any,
    sector: str,
    sector_avg_pe: float,
    div_yield: Any,
    momentum_score: int,
    prediction_score: int,
    market_regime: str,
    macro_overlay: List[str],
    conclusion: str,
) -> str:
    """Build the standard stock buy/hold/sell format."""
    clean = str(symbol).replace(".NS", "").replace(".BO", "")
    price_str = f"Rs.{price:,.2f}" if price is not None and isinstance(price, (int, float)) else "N/A"
    pe_str = f"{pe:.1f}" if pe is not None else "N/A"
    div_str = f"{div_yield}%" if div_yield is not None else "N/A"

    lines = [
        f"**STOCK ANALYSIS: {clean}**",
        "",
        f"**Decision:** {decision}",
        f"**Confidence:** {confidence}%",
        f"**Current Price:** {price_str}",
        "",
        "**Fundamentals:**",
        f"• P/E Ratio   : {pe_str} (Sector avg: ~{sector_avg_pe:.1f})",
        f"• Sector      : {sector}",
        f"• Dividend    : {div_str}",
        "",
        "**Technical Signals:**",
        f"• Momentum    : {momentum_score}/100",
        f"• Prediction  : {prediction_score}/100",
        f"• Market Regime: {market_regime}",
        "",
        "**Macro Overlay (Live):**",
    ]
    for m in macro_overlay[:3]:
        lines.append(f"• {m}")
    if not macro_overlay:
        lines.append("• Live macro data unavailable.")
    lines.extend(["", "**Conclusion:**", conclusion, "", "**Risk Note:** Use this as decision support only."])
    return "\n".join(lines)


def _format_portfolio_analysis(
    stocks: List[Dict[str, Any]],
    allocations: List[Dict[str, Any]],
    sector_breakdown: Dict[str, Any],
    diversification_score: float,
    risk_level: str,
    suggestions: str,
    macro_overlay: List[str],
) -> str:
    """Build the standard portfolio analysis format."""
    lines = [
        "**PORTFOLIO ANALYSIS**",
        "",
        "**Holdings:**",
        "| Stock    | Price    | Weight | Sector           |",
        "|----------|----------|--------|------------------|",
    ]
    by_sym = {s.get("symbol"): s for s in stocks if s.get("symbol")}
    weights = {a["symbol"]: a["weight_percent"] for a in allocations if a.get("symbol")}
    sector_weights: Dict[str, float] = {}
    for a in allocations:
        sym = a.get("symbol", "")
        w = weights.get(sym, 0)
        d = by_sym.get(sym) or {}
        sec = str(d.get("sector") or "N/A")
        sector_weights[sec] = sector_weights.get(sec, 0) + w
    for a in allocations[:10]:
        sym = a.get("symbol", "")
        w = weights.get(sym, 0)
        d = by_sym.get(sym) or {}
        sec = str(d.get("sector") or "N/A")
        name = str(sym).replace(".NS", "").replace(".BO", "")
        price = d.get("price", "N/A")
        price_str = f"Rs.{price:,.2f}" if isinstance(price, (int, float)) else str(price)
        lines.append(f"| {name:<8} | {price_str:<8} | {w:.0f}%    | {sec:<16} |")

    lines.extend(["", "**Sector Breakdown:**"])
    for sec, pct in sorted(sector_weights.items(), key=lambda x: -x[1]):
        lines.append(f"• {sec}: {round(pct)}%")

    lines.extend(["", "**Macro Risk Overlay (Live):**"])
    for m in macro_overlay[:3]:
        lines.append(f"• {m}")
    if not macro_overlay:
        lines.append("• Live macro data unavailable.")

    div_label = "Good" if diversification_score >= 60 else "Moderate" if diversification_score >= 40 else "Poor"
    dominant = max(allocations, key=lambda a: weights.get(a.get("symbol", ""), 0)) if allocations else None
    dom_name = str(dominant.get("symbol", "")).replace(".NS", "").replace(".BO", "") if dominant else ""
    dom_w = weights.get(dominant.get("symbol", ""), 0) if dominant else 0
    conc_label = f"{dom_name} at {dom_w:.0f}%" if dom_w >= 40 else "None"
    lines.extend([
        "",
        "**Risk Assessment:**",
        f"• Diversification : {div_label}",
        f"• Concentration   : {conc_label}",
        f"• Macro Exposure  : {risk_level} risk",
        "",
        "**Recommendations:**",
        suggestions or "Maintain discipline with position sizing.",
        "",
        "**Risk Note:** Not personalised financial advice.",
    ])
    return "\n".join(lines)


COMMODITY_ASSETS: Dict[str, Dict[str, str]] = {
    "gold": {"name": "Gold (Commodity)", "ticker": "GC=F", "sector": "Commodity"},
    "silver": {"name": "Silver (Commodity)", "ticker": "SI=F", "sector": "Commodity"},
    "oil": {"name": "Crude Oil (Commodity)", "ticker": "CL=F", "sector": "Commodity"},
    "bitcoin": {"name": "Bitcoin", "ticker": "BTC-USD", "sector": "Crypto"},
    "btc": {"name": "Bitcoin", "ticker": "BTC-USD", "sector": "Crypto"},
}

def handle_neutral_macro_scenario(signals, causal_insights):
    from datetime import datetime, timezone, timedelta

    IST = timezone(timedelta(hours=5, minutes=30))
    timestamp = datetime.now(IST).strftime("%d/%m/%Y, %I:%M:%S %p IST")

    bond = signals.get("bond_yield", {}) or {}
    crude = signals.get("crude_oil", {}) or {}
    inr = signals.get("usd_inr", {}) or {}
    gold = signals.get("gold", {}) or {}
    vix = signals.get("india_vix", {}) or {}

    response = f"""**MACRO SCENARIO: ALL SIGNALS NEUTRAL**

**What "Neutral Macro" Means:**
When all macro signals show minimal movement near baseline, 
it signals a low-volatility, range-bound environment. 
No strong directional catalyst is present from the macro side. 
This is generally positive for equities as it removes the 
uncertainty premium from valuations.

**Current Live Signals for Reference:**
- Bond Yield : {round(float(bond.get('current_value', 0)), 2)} ({float(bond.get('change_pct', 0)):+.2f}%)
- Crude Oil  : {round(float(crude.get('current_value', 0)), 2)} ({float(crude.get('change_pct', 0)):+.2f}%)
- USD/INR    : {round(float(inr.get('current_value', 0)), 2)} ({float(inr.get('change_pct', 0)):+.2f}%)
- Gold       : {round(float(gold.get('current_value', 0)), 2)} ({float(gold.get('change_pct', 0)):+.2f}%)
- India VIX  : {round(float(vix.get('current_value', 0)), 2)} ({float(vix.get('change_pct', 0)):+.2f}%)

**What to Do in a Neutral Macro Environment:**
- Focus shifts from macro timing to stock fundamentals
- Quality earnings, revenue growth, and management matter more
- Good time for systematic SIP investments
- Sector rotation slows — broad market moves together
- Mid-caps tend to outperform in low-VIX environments

**Sectors that Outperform in Neutral Macro:**
- Quality large-caps across IT, Banking, FMCG
- Dividend-paying stocks benefit from stability
- Growth stocks recover as uncertainty premium fades

**Data as of:** {timestamp}"""
    return {"message": response}


def handle_sector_safety_ranking(signals, causal_insights):
    from datetime import datetime, timezone, timedelta

    IST = timezone(timedelta(hours=5, minutes=30))
    timestamp = datetime.now(IST).strftime("%d/%m/%Y, %I:%M:%S %p IST")

    bond = signals.get("bond_yield", {}) or {}
    crude = signals.get("crude_oil", {}) or {}
    inr = signals.get("usd_inr", {}) or {}
    gold = signals.get("gold", {}) or {}
    vix = signals.get("india_vix", {}) or {}

    bond_chg = float(bond.get("change_pct", 0) or 0)
    crude_chg = float(crude.get("change_pct", 0) or 0)
    inr_chg = float(inr.get("change_pct", 0) or 0)
    gold_chg = float(gold.get("change_pct", 0) or 0)
    vix_val = float(vix.get("current_value", 0) or 0)
    vix_chg = float(vix.get("change_pct", 0) or 0)

    # Score each sector
    scores = {
        "FMCG": 0,
        "Pharma": 0,
        "IT": 0,
        "Banking": 0,
        "Energy": 0,
        "Aviation/Logistics": 0,
    }
    reasons = {k: [] for k in scores}

    # FMCG scoring
    if vix_chg > 3:
        scores["FMCG"] += 1
        reasons["FMCG"].append("defensive demand in high VIX")
    if gold_chg > 0.5:
        scores["FMCG"] += 1
        reasons["FMCG"].append("risk-off favors defensives")
    if crude_chg > 1:
        scores["FMCG"] -= 1
        reasons["FMCG"].append("crude up = input cost pressure")

    # Pharma scoring
    if inr_chg > 0.3:
        scores["Pharma"] += 2
        reasons["Pharma"].append("weak INR boosts export revenues")
    if vix_chg > 3:
        scores["Pharma"] += 1
        reasons["Pharma"].append("defensive positioning in fear")

    # IT scoring
    if inr_chg > 0.3:
        scores["IT"] += 2
        reasons["IT"].append("weak INR = export revenue tailwind")
    if bond_chg > 0.5:
        scores["IT"] -= 1
        reasons["IT"].append("rising yields compress valuations")
    if vix_chg > 5:
        scores["IT"] -= 1
        reasons["IT"].append("high VIX = growth sell-off risk")

    # Banking scoring
    if bond_chg > 0.3:
        scores["Banking"] += 1
        reasons["Banking"].append("rising yields expand NIM")
    if vix_val > 20 and vix_chg > 3:
        scores["Banking"] -= 1
        reasons["Banking"].append("high VIX = NPA risk perception")

    # Energy scoring
    if crude_chg > 1:
        scores["Energy"] += 2
        reasons["Energy"].append("rising crude = revenue positive")
    elif crude_chg < -1:
        scores["Energy"] -= 2
        reasons["Energy"].append("falling crude = revenue pressure")

    # Aviation scoring
    if crude_chg > 1:
        scores["Aviation/Logistics"] -= 2
        reasons["Aviation/Logistics"].append("rising crude = fuel cost pressure")
    elif crude_chg < -1:
        scores["Aviation/Logistics"] += 2
        reasons["Aviation/Logistics"].append("falling crude = cost relief")

    # Sort by score descending
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    table_rows = ""
    for i, (sector, score) in enumerate(ranked, 1):
        reason = reasons[sector][0] if reasons[sector] else "Neutral macro impact"
        sign = "+" if score >= 0 else ""
        table_rows += f"| {i} | {sector:<22} | {sign}{score:>2}  | {reason:<35} |\n"

    top_sectors = [s for s, sc in ranked if sc > 0][:3]
    avoid_sectors = [s for s, sc in ranked if sc < 0]
    top_str = ", ".join(top_sectors) if top_sectors else "No clear favorites"
    avoid_str = ", ".join(avoid_sectors) if avoid_sectors else "None"

    response = f"""**SECTOR SAFETY RANKING — CURRENT MACRO**

**Live Signals Used:**
- Bond Yield : {round(float(bond.get('current_value', 0)), 2)} ({bond_chg:+.2f}%)
- Crude Oil  : {round(float(crude.get('current_value', 0)), 2)} ({crude_chg:+.2f}%)
- USD/INR    : {round(float(inr.get('current_value', 0)), 2)} ({inr_chg:+.2f}%)
- Gold       : {round(float(gold.get('current_value', 0)), 2)} ({gold_chg:+.2f}%)
- India VIX  : {round(float(vix.get('current_value', 0)), 2)} ({vix_chg:+.2f}%)

**Sector Rankings (Safest to Riskiest):**

| Rank | Sector                 | Score | Key Reason                          |
|------|------------------------|-------|-------------------------------------|
{table_rows}
**Top Sectors Right Now    :** {top_str}
**Sectors to Be Cautious  :** {avoid_str}

**Data as of:** {timestamp}"""
    return {"message": response}


def _extract_portfolio_allocations(query: str) -> List[Dict[str, Any]]:
    """
    Parse simple portfolio input patterns:
      "Reliance 40%"
      "TCS 30%"
      "gold 20%"  -> GC=F (commodity, never GOLDENTOBC)
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
        name_clean = name.strip().lower()
        # Commodity/crypto assets: never resolve to NSE stock
        if name_clean in COMMODITY_ASSETS:
            info = COMMODITY_ASSETS[name_clean]
            allocs.append({
                "symbol": info["ticker"],
                "weight_percent": w,
                "asset_type": "commodity",
                "display_name": info["name"],
                "sector": info["sector"],
            })
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
    if len(symbols) < 2:
        return None

    rows: List[Dict[str, Any]] = []
    has_commodity = False
    has_stock = False

    for raw in symbols:
        # Commodity tickers (from COMMODITY_MAP) are handled first and never fall through to stock lookup.
        if raw in _COMMODITY_TICKERS:
            has_commodity = True
            sym = raw
            try:
                from app.utils.datetime_utils import get_ist_now

                def _fetch():
                    hist_1y = fetch_history(sym, period="1y", ttl=60)
                    if hist_1y is None or hist_1y.empty:
                        return None

                    curr = float(hist_1y["Close"].iloc[-1])
                    # Today change
                    today_change = None
                    if len(hist_1y) >= 2:
                        prev = float(hist_1y["Close"].iloc[-2])
                        if prev:
                            today_change = ((curr - prev) / prev) * 100

                    # 52W High / Low
                    high_52w = float(hist_1y["High"].max())
                    low_52w = float(hist_1y["Low"].min())

                    # 1M / 3M / YTD change
                    hist_1m = fetch_history(sym, period="1mo", ttl=60)
                    hist_3m = fetch_history(sym, period="3mo", ttl=60)
                    year = get_ist_now().year
                    hist_ytd = fetch_history(sym, start=f"{year}-01-01", period="1y", ttl=60)

                    def _series_change(h):
                        try:
                            if h is not None and not h.empty:
                                base = float(h["Close"].iloc[0])
                                if base:
                                    return ((curr - base) / base) * 100
                        except Exception:
                            return None
                        return None

                    chg_1m = _series_change(hist_1m)
                    chg_3m = _series_change(hist_3m)
                    chg_ytd = _series_change(hist_ytd)

                    return {
                        "price": curr,
                        "high_52w": high_52w,
                        "low_52w": low_52w,
                        "today_change": today_change,
                        "change_1m": chg_1m,
                        "change_3m": chg_3m,
                        "change_ytd": chg_ytd,
                    }

                metrics = await anyio.to_thread.run_sync(_fetch)
            except Exception:
                metrics = None

            if not isinstance(metrics, dict):
                rows.append(
                    {
                        "symbol": sym,
                        "name": str(sym),
                        "assetType": "Commodity",
                        "price": None,
                        "pe": None,
                        "dividendYield": None,
                        "sector": None,
                        "marketCap": None,
                        "high_52w": None,
                        "low_52w": None,
                        "todayChange": None,
                        "change1m": None,
                        "change3m": None,
                        "changeYtd": None,
                    }
                )
                continue

            rows.append(
                {
                    "symbol": sym,
                    "name": str(sym),
                    "assetType": "Commodity",
                    "price": metrics.get("price"),
                    "pe": None,
                    "dividendYield": None,
                    "sector": "Commodity",
                    "marketCap": None,
                    "high_52w": metrics.get("high_52w"),
                    "low_52w": metrics.get("low_52w"),
                    "todayChange": metrics.get("today_change"),
                    "change1m": metrics.get("change_1m"),
                    "change3m": metrics.get("change_3m"),
                    "changeYtd": metrics.get("change_ytd"),
                    # Raw metrics for comparison logic
                    "price_float": metrics.get("price"),
                    "pe_float": None,
                    "div_yield_float": None,
                    "market_cap_float": None,
                    "today_change_float": metrics.get("today_change"),
                    "market_cap_display": None,
                    "dividendYield_display": None,
                    "price_display": None,
                }
            )
            continue

        # Stock path (existing behaviour)
        sym = _normalize_symbol_maybe(raw)
        if not sym:
            rows.append(
                {
                    "symbol": raw,
                    "name": str(raw).replace(".NS", "").replace(".BO", ""),
                    "assetType": "Stock",
                    "price": None,
                    "pe": None,
                    "dividendYield": None,
                    "sector": None,
                    "marketCap": None,
                    "high_52w": None,
                    "low_52w": None,
                    "todayChange": None,
                    "change1m": None,
                    "change3m": None,
                    "changeYtd": None,
                }
            )
            continue

        has_stock = True
        metrics = await anyio.to_thread.run_sync(get_stock_metrics_safe, sym)
        if not isinstance(metrics, dict):
            rows.append(
                {
                    "symbol": sym,
                    "name": str(sym).replace(".NS", "").replace(".BO", ""),
                    "assetType": "Stock",
                    "price": None,
                    "pe": None,
                    "dividendYield": None,
                    "sector": None,
                    "marketCap": None,
                    "high_52w": None,
                    "low_52w": None,
                    "todayChange": None,
                    "change1m": None,
                    "change3m": None,
                    "changeYtd": None,
                }
            )
            continue

        rows.append(
            {
                "symbol": sym,
                "name": str(sym).replace(".NS", "").replace(".BO", ""),
                "assetType": "Stock",
                # Display fields (numeric for formatting helpers)
                "price": metrics.get("price_float"),
                "pe": metrics.get("pe_float"),
                "dividendYield": metrics.get("div_yield_float"),
                "sector": metrics.get("sector"),
                "marketCap": metrics.get("market_cap_float"),
                "high_52w": metrics.get("fifty_two_high"),
                "low_52w": metrics.get("fifty_two_low"),
                "todayChange": metrics.get("today_change_float"),
                "change1m": None,
                "change3m": None,
                "changeYtd": None,
                # Raw metrics for winner logic
                "price_float": metrics.get("price_float"),
                "pe_float": metrics.get("pe_float"),
                "div_yield_float": metrics.get("div_yield_float"),
                "market_cap_float": metrics.get("market_cap_float"),
                "today_change_float": metrics.get("today_change_float"),
                "market_cap_display": metrics.get("market_cap"),
                "dividendYield_display": metrics.get("div_yield"),
                "price_display": metrics.get("price"),
            }
        )

    # Caller is responsible for enforcing minimum valid rows; keep rows even if < 2 for better messaging.

    # Leaders and interpretation are computed defensively; any failure should not crash the advisor.
    interpretation: List[str] = []
    valuation_leader: Optional[Dict[str, Any]] = None
    income_leader: Optional[Dict[str, Any]] = None
    size_leader: Optional[Dict[str, Any]] = None
    growth_candidate: Optional[Dict[str, Any]] = None
    conclusion_lines: List[str] = []
    best_today: Optional[Dict[str, Any]] = None
    best_1m: Optional[Dict[str, Any]] = None
    best_3m: Optional[Dict[str, Any]] = None
    overall_trend_text: Optional[str] = None

    try:
        # Prepare numeric fields from *_float helpers
        for r in rows:
            r["peNumeric"] = r.get("pe_float")
            r["dividendYieldNumeric"] = r.get("div_yield_float")
            r["marketCapNumeric"] = r.get("market_cap_float")
            r["todayChangeNumeric"] = r.get("today_change_float")

        # Stock-only style leaders (valuation, income, size, momentum)
        stock_rows = [r for r in rows if r.get("assetType") != "Commodity"]
        if stock_rows:
            val_candidates = [r for r in stock_rows if (r.get("peNumeric") is not None and r.get("peNumeric") > 0)]
            if val_candidates:
                valuation_leader = min(val_candidates, key=lambda x: x.get("peNumeric", float("inf")))

            inc_candidates = [r for r in stock_rows if r.get("dividendYieldNumeric") is not None]
            if inc_candidates:
                income_leader = max(inc_candidates, key=lambda x: x.get("dividendYieldNumeric", 0.0))

            size_candidates = [r for r in stock_rows if r.get("marketCapNumeric") is not None]
            if size_candidates:
                size_leader = max(size_candidates, key=lambda x: x.get("marketCapNumeric", 0.0))

            mom_candidates = [r for r in stock_rows if r.get("todayChangeNumeric") is not None]
            momentum_leader = max(mom_candidates, key=lambda x: x.get("todayChangeNumeric", 0.0)) if mom_candidates else None
        else:
            momentum_leader = None

        if valuation_leader:
            interpretation.append(f"{valuation_leader['name']} has the lowest valuation based on P/E among the compared stocks.")
        if income_leader:
            interpretation.append(f"{income_leader['name']} offers the highest dividend yield in this group.")
        if size_leader:
            interpretation.append(f"{size_leader['name']} is the largest company by reported market capitalisation.")

        # Growth candidate: highest P/E (market pricing in growth)
        if stock_rows:
            growth_candidates = [r for r in stock_rows if (r.get("peNumeric") is not None and r.get("peNumeric") > 0)]
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
        if not conclusion_lines and stock_rows:
            conclusion_lines.append("- No clear standouts on valuation, dividends, or size based on available data.")

        # Commodity / mixed comparison winners (price-based performance)
        if has_commodity:
            # Best performers based on price changes
            today_candidates = [r for r in rows if isinstance(r.get("todayChange"), (int, float))]
            if today_candidates:
                best_today = max(today_candidates, key=lambda x: x.get("todayChange", 0.0))

            m1_candidates = [r for r in rows if isinstance(r.get("change1m"), (int, float))]
            if m1_candidates:
                best_1m = max(m1_candidates, key=lambda x: x.get("change1m", 0.0))

            m3_candidates = [r for r in rows if isinstance(r.get("change3m"), (int, float))]
            if m3_candidates:
                best_3m = max(m3_candidates, key=lambda x: x.get("change3m", 0.0))

            # Macro-aware overall trend from cross-market signals (best-effort)
            try:
                from app.services.cross_market_service import get_cross_market_signals

                sigs = get_cross_market_signals() or {}
                gold = sigs.get("gold") or {}
                crude = sigs.get("wti_crude") or sigs.get("crude_oil") or {}
                usd_inr = sigs.get("usd_inr") or {}

                parts: List[str] = []
                if isinstance(gold, dict) and gold.get("current_value") is not None:
                    parts.append(
                        f"Gold is around {float(gold['current_value']):.2f}, "
                        f"{'up' if (gold.get('change_pct') or 0) > 0 else 'down' if (gold.get('change_pct') or 0) < 0 else 'flat'} "
                        f"{abs(float(gold.get('change_pct') or 0)):.2f}% today."
                    )
                if isinstance(crude, dict) and crude.get("current_value") is not None:
                    parts.append(
                        f"Crude oil trades near {float(crude['current_value']):.2f}, "
                        f"{'rising' if (crude.get('change_pct') or 0) > 0 else 'easing' if (crude.get('change_pct') or 0) < 0 else 'flat'} on the day."
                    )
                if isinstance(usd_inr, dict) and usd_inr.get("current_value") is not None:
                    parts.append(
                        f"USD/INR is around {float(usd_inr['current_value']):.2f}, "
                        f"{'indicating a weaker rupee' if (usd_inr.get('change_pct') or 0) > 0 else 'suggesting a stable to stronger rupee' if (usd_inr.get('change_pct') or 0) < 0 else 'showing a steady currency pair'}."
                    )
                overall_trend_text = " ".join(parts) if parts else None
            except Exception:
                overall_trend_text = None

    except Exception:
        # If anything goes wrong in leader/interpretation logic, fall back to a neutral explanation
        interpretation = []
        valuation_leader = None
        income_leader = None
        size_leader = None
        growth_candidate = None
        momentum_leader = None
        conclusion_lines = [
            "- Comparison signals are mixed or temporarily unavailable based on the fetched data.",
            "- Consider reviewing each asset's fundamentals and your own risk profile before deciding.",
        ]

    return {
        "rows": rows,
        "has_commodity": has_commodity,
        "has_stock": has_stock,
        "leaders": {
            "valuation_leader": valuation_leader,
            "income_leader": income_leader,
            "size_leader": size_leader,
            "growth_candidate": growth_candidate,
            "momentum_leader": momentum_leader,
            "best_today": best_today,
            "best_1m": best_1m,
            "best_3m": best_3m,
            "overall_trend_text": overall_trend_text,
        },
        "interpretation": interpretation,
        "conclusion": conclusion_lines,
    }


def _is_commodity_ticker(sym: str) -> bool:
    return str(sym).upper() in ("GC=F", "SI=F", "CL=F", "BTC-USD")


async def _portfolio_allocation_analysis(allocs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not allocs:
        return None

    from app.services.stock_service import get_stock_detail
    from app.utils.yfinance_wrapper import fetch_history

    # Normalize weights
    weights = [float(a["weight_percent"]) for a in allocs if a.get("symbol")]
    total = sum(weights) if weights else 0.0
    if total <= 0:
        return None

    normalized = [{"symbol": a["symbol"], "weight": float(a["weight_percent"]) / total} for a in allocs]

    # Fetch details with timeout
    details: List[Dict[str, Any]] = []
    sector_breakdown: Dict[str, int] = {}
    for a in allocs[:15]:
        sym = a.get("symbol")
        if not sym:
            continue
        w = float(a.get("weight_percent", 0)) / total
        if _is_commodity_ticker(sym):
            # Fetch commodity price from yfinance
            try:
                hist = await _run_sync_with_timeout(
                    fetch_history, sym, period="5d", interval="1d", ttl=60, timeout_s=10.0,
                )
                price = None
                if hist is not None and not hist.empty and "Close" in hist:
                    price = float(hist["Close"].iloc[-1])
                info = next((v for v in COMMODITY_ASSETS.values() if v["ticker"] == sym), {})
                d_out = {
                    "symbol": sym,
                    "price": price,
                    "sector": info.get("sector", "Commodity"),
                    "pe": None,
                }
                details.append(d_out)
                sec = d_out.get("sector", "Commodity")
                sector_breakdown[sec] = sector_breakdown.get(sec, 0) + 1
            except Exception:
                d_out = {"symbol": sym, "price": None, "sector": "Commodity", "pe": None}
                details.append(d_out)
                sector_breakdown["Commodity"] = sector_breakdown.get("Commodity", 0) + 1
            continue
        sym_norm = _normalize_symbol_maybe(sym)
        if not sym_norm:
            continue
        d = await _run_sync_with_timeout(get_stock_detail, sym_norm, timeout_s=10.0)
        if not isinstance(d, dict) or d.get("error"):
            continue
        d_out = {"symbol": d.get("symbol") or sym_norm, "price": d.get("price"), "sector": d.get("sector"), "pe": d.get("pe")}
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

    user_msg = q.lower().strip()

    # HARDCODED CHECK 1 — Neutral macro scenario
    NEUTRAL_PATTERNS = [
        "all macro signals are neutral",
        "signals are neutral",
        "macro signals are neutral",
        "all signals neutral",
        "all signals are neutral",
        "what if signals are neutral",
        "what if all macro",
        "neutral macro",
        "signals neutral",
        "macro neutral",
    ]
    if any(p in user_msg for p in NEUTRAL_PATTERNS):
        from app.services.cross_market_service import get_cross_market_signals
        from app.services.causality_engine import interpret_causality

        sigs = get_cross_market_signals() or {}
        causal = interpret_causality(sigs) if sigs else []
        mapped = {
            "bond_yield": sigs.get("us_10y_yield"),
            "crude_oil": sigs.get("wti_crude"),
            "usd_inr": sigs.get("usd_inr"),
            "gold": sigs.get("gold"),
            "india_vix": sigs.get("india_vix"),
        }
        return handle_neutral_macro_scenario(mapped, causal), {"last_intent": "macro_analysis"}

    # HARDCODED CHECK 2 — Sector safety ranking
    SECTOR_SAFETY_PATTERNS = [
        "safest sector",
        "safest sectors",
        "sectors to invest",
        "best sectors",
        "which sectors are safe",
        "sectors safe",
        "where to invest",
        "which sectors to buy",
        "safe sectors",
        "sectors right now",
    ]
    if any(p in user_msg for p in SECTOR_SAFETY_PATTERNS):
        from app.services.cross_market_service import get_cross_market_signals
        from app.services.causality_engine import interpret_causality

        sigs = get_cross_market_signals() or {}
        causal = interpret_causality(sigs) if sigs else []
        mapped = {
            "bond_yield": sigs.get("us_10y_yield"),
            "crude_oil": sigs.get("wti_crude"),
            "usd_inr": sigs.get("usd_inr"),
            "gold": sigs.get("gold"),
            "india_vix": sigs.get("india_vix"),
        }
        return handle_sector_safety_ranking(mapped, causal), {"last_intent": "macro_analysis"}

    ql = q.lower()
    raw_syms_for_early = get_raw_parser_symbols(q, context=ctx)

    def _resolve_primary_symbol_early() -> Optional[str]:
        if raw_syms_for_early:
            return _normalize_symbol_maybe(raw_syms_for_early[0])
        toks = re.findall(r"[A-Za-z]{2,12}", q)
        for t in toks:
            sym = _normalize_symbol_maybe(t)
            if sym and (sym.endswith(".NS") or sym.endswith(".BO")):
                return sym
        return None

    def _signal_key_from_text(text: str) -> str:
        t = (text or "").lower()
        if re.search(r"\b(interest rate|rates|rbi)\b", t):
            return "us_10y_yield"
        if re.search(r"\b(crude|oil)\b", t):
            return "wti_crude"
        if re.search(r"\b(rupee|currency|forex|usd)\b", t):
            return "usd_inr"
        if re.search(r"\b(volatility|fear|vix)\b", t):
            return "india_vix"
        if re.search(r"\b(gold|safe haven)\b", t):
            return "gold"
        return _detect_primary_macro_signal(text)

    # Step 2/3 (strict): macro-driven stock analysis OR stock+signal questions route here before portfolio/comparison.
    is_macro_driven_stock = bool(
        re.search(r"\b(macro analysis of|macro-driven analysis of|macro outlook for|macro view on|macro-driven)\b", ql)
    )
    is_stock_signal_question = bool(
        re.search(
            r"\b(is\s+.+\b(good buy|a buy|worth buying|good investment|worth investing)\b.*\b(when|if)\b|"
            r"(how does|impact of|effect of|what does).+\b(affect|impact|mean for)\b)\b",
            ql,
        )
    )
    if is_macro_driven_stock or is_stock_signal_question:
        sym_norm_early = _resolve_primary_symbol_early()
        if sym_norm_early:
            from app.services.stock_service import get_stock_detail
            from app.services.cross_market_service import get_cross_market_signals
            from app.utils.datetime_utils import get_ist_timestamp

            data_timestamp = get_ist_timestamp()
            detail = await _run_sync_with_timeout(get_stock_detail, sym_norm_early, timeout_s=10.0) or {}
            signals = get_cross_market_signals() or {}
            clean = sym_norm_early.replace(".NS", "").replace(".BO", "")
            sector = (detail or {}).get("sector") or "N/A"
            price = (detail or {}).get("price")
            price_str = f"Rs.{float(price):,.2f}" if isinstance(price, (int, float)) else "N/A"

            if is_macro_driven_stock:
                def _sig_row(key: str) -> Tuple[str, str, str, str]:
                    s = signals.get(key) if isinstance(signals, dict) else None
                    if not s or not isinstance(s, dict):
                        return (_MACRO_LABELS.get(key, key), "N/A", "N/A", "LOW direct impact")
                    cv = s.get("current_value")
                    cp = s.get("change_pct")
                    try:
                        cv = float(cv) if cv is not None else None
                        cp = float(cp) if cp is not None else None
                    except Exception:
                        cv, cp = None, None
                    val = f"{cv:.2f}" if cv is not None else "N/A"
                    chg = f"{cp:+.2f}%" if cp is not None else "N/A"
                    # Simple sector-aware labels per spec examples
                    base = clean.upper()
                    if base == "RELIANCE":
                        imp = {
                            "wti_crude": "POSITIVE — revenue driver" if (cp or 0) > 0 else "NEGATIVE — price pressure",
                            "usd_inr": "MIXED — retail/telecom",
                            "us_10y_yield": "NEUTRAL (low impact)",
                            "india_vix": "CAUTION — broad market",
                            "gold": "LOW direct impact",
                        }.get(key, "LOW impact")
                    elif base == "ONGC":
                        imp = {
                            "wti_crude": "POSITIVE — direct revenue" if (cp or 0) > 0 else "NEGATIVE — realization risk",
                            "usd_inr": "POSITIVE — USD revenues",
                            "us_10y_yield": "LOW impact",
                            "india_vix": "CAUTION",
                            "gold": "LOW direct impact",
                        }.get(key, "LOW impact")
                    elif base in {"TCS", "INFY"}:
                        imp = {
                            "us_10y_yield": "NEGATIVE — discount rate",
                            "usd_inr": "POSITIVE — export revenue",
                            "india_vix": "CAUTION",
                            "wti_crude": "LOW impact",
                            "gold": "LOW impact",
                        }.get(key, "LOW impact")
                    elif base in {"HDFCBANK"}:
                        imp = {
                            "us_10y_yield": "POSITIVE — NIM expansion",
                            "india_vix": "CAUTION — liquidity",
                            "usd_inr": "LOW impact",
                            "wti_crude": "LOW impact",
                            "gold": "LOW impact",
                        }.get(key, "LOW impact")
                    else:
                        imp = "LOW impact"
                    return (_MACRO_LABELS.get(key, key), val, chg, imp)

                rows = [_sig_row("wti_crude"), _sig_row("usd_inr"), _sig_row("us_10y_yield"), _sig_row("india_vix"), _sig_row("gold")]
                lines = [
                    f"**MACRO-DRIVEN STOCK ANALYSIS: {clean}**",
                    "",
                    f"**Current Price:** {price_str}",
                    f"**Sector:** {sector}",
                    "",
                    f"**All Macro Signals vs {clean}:**",
                    "",
                    f"| Signal | Value | Change | Impact on {clean} |",
                    "|--------|-------|--------|---------------------------|",
                ]
                for sig, val, chg, imp in rows:
                    lines.append(f"| {sig} | {val} | {chg} | {imp} |")
                net = "Neutral"
                if any("POSITIVE" in r[3] for r in rows[:2]):
                    net = "Positive"
                if any("NEGATIVE" in r[3] for r in rows):
                    net = "Negative"
                lines.extend([
                    "",
                    f"**Net Macro Score for {clean}:** {net}",
                    "",
                    "**Conclusion:**",
                    "This combines live macro signals with sector sensitivity. Use it as context for risk sizing and stock selection.",
                    "",
                    f"**Data as of:** {data_timestamp}",
                ])
                return _chat_response({"source": "stock_analysis", "result": {"symbol": sym_norm_early}, "message": "\n".join(lines), "query": q}, {"last_symbol": sym_norm_early, "last_intent": "stock_analysis"})

            # Stock-signal / good-buy-when format (stock + relevant macro signal)
            signal_key = _signal_key_from_text(q)
            sig = (signals or {}).get(signal_key) if isinstance(signals, dict) else None
            sig_val = "N/A"
            sig_chg = "N/A"
            sig_dir = None
            if isinstance(sig, dict):
                try:
                    sig_val = f"{float(sig.get('current_value')):.2f}"
                    sig_chg = f"{float(sig.get('change_pct') or 0):+.2f}%"
                    sig_dir = sig.get("direction") or ("up" if float(sig.get("change_pct") or 0) > 0 else "down" if float(sig.get("change_pct") or 0) < 0 else "flat")
                except Exception:
                    pass

            def _other_signal_line(key: str) -> Optional[str]:
                s2 = (signals or {}).get(key) if isinstance(signals, dict) else None
                if not isinstance(s2, dict) or s2.get("current_value") is None:
                    return None
                try:
                    cv2 = float(s2.get("current_value"))
                    cp2 = float(s2.get("change_pct") or 0)
                except Exception:
                    return None
                impact = "sector impact"
                if sector and "technology" in str(sector).lower():
                    if key == "usd_inr":
                        impact = "export revenue tailwind" if cp2 > 0 else "export revenue headwind" if cp2 < 0 else "neutral"
                    if key == "us_10y_yield":
                        impact = "valuation headwind" if cp2 > 0 else "valuation tailwind" if cp2 < 0 else "neutral — no pressure"
                    if key == "wti_crude":
                        impact = "low direct impact on IT"
                if sector and "financial" in str(sector).lower():
                    if key == "us_10y_yield":
                        impact = "NIM expansion positive" if cp2 > 0 else "NIM compression risk" if cp2 < 0 else "stable margin outlook"
                    if key == "india_vix":
                        impact = "elevated fear — reduce size" if cv2 >= 20 and cp2 > 0 else "fear easing — cautious entry" if cv2 >= 20 and cp2 < 0 else "calm market — normal sizing"
                    if key == "usd_inr":
                        impact = "low direct impact on domestic bank"
                return f"• {_MACRO_LABELS.get(key, key)} {cv2:.2f} ({cp2:+.2f}%) — {impact}"

            # Stock-signal narratives (3–4 sentences) with provided templates
            narrative = None
            base = clean.upper()
            if base == "HDFCBANK" and signal_key == "us_10y_yield":
                narrative = (
                    f"Rising interest rates expand HDFC Bank's Net Interest Margin (NIM) as lending rates reprice faster than "
                    f"deposit costs. However very high rates can slow loan growth and increase NPAs. "
                    f"Current yield at {sig_val} with flat movement suggests a stable rate environment — "
                    f"neutral to mildly positive for HDFC Bank's margins."
                )
            if base == "HDFCBANK" and signal_key == "india_vix":
                narrative = (
                    "High VIX signals market fear which can trigger FII outflows from banking stocks. "
                    "HDFC Bank as a large-cap bank is typically sold first in risk-off environments. "
                    "Current VIX above 20 warrants caution on position sizing."
                )
            if base == "ONGC" and signal_key == "wti_crude":
                narrative = (
                    "Rising crude is directly positive for ONGC as an upstream oil producer. "
                    "Higher crude prices increase revenue realization per barrel produced. "
                    "At $84 crude is above ONGC's breakeven, supporting strong cash flows. "
                    "Watch for government windfall tax risk above $90."
                )
            if base == "TCS" and signal_key == "wti_crude":
                narrative = (
                    "Crude oil has minimal direct impact on TCS as an IT services company with low physical input costs. "
                    "However rising crude increases inflation risk which can lead to rate hikes, indirectly pressuring IT growth valuations. "
                    f"Current crude at {sig_val} with {sig_chg} is a low indirect risk."
                )
            if base in {"TCS", "INFY"} and signal_key == "us_10y_yield":
                pe_txt = f"{(detail or {}).get('pe')}" if (detail or {}).get("pe") is not None else "N/A"
                narrative = (
                    "Rising US bond yields increase the discount rate on future earnings, compressing valuations of high-PE growth stocks like IT companies. "
                    f"{base} at P/E {pe_txt} is relatively protected versus higher-PE peers. "
                    "Flat yield today is neutral — no incremental valuation pressure."
                )
            if base in {"TCS", "INFY"} and signal_key == "usd_inr":
                narrative = (
                    "Weaker INR directly benefits IT exporters like TCS as USD revenues convert to more rupees. "
                    f"Current INR at {sig_val}, {sig_chg} today provides a mild export tailwind. "
                    "Each 1% INR depreciation adds roughly 0.3-0.5% to IT company operating margins."
                )
            if base == "RELIANCE" and signal_key == "wti_crude":
                narrative = (
                    "Crude oil has a complex dual impact on Reliance. "
                    "Rising crude benefits the upstream O&G and refining segments but increases costs for the petrochemicals business. "
                    "Net impact is mildly positive at current levels as refining margins tend to expand with crude."
                )
            if not narrative:
                narrative = (
                    f"This macro signal influences {sector} mainly through funding costs, demand conditions, and investor risk appetite. "
                    f"With {_MACRO_LABELS.get(signal_key, signal_key)} {('rising' if sig_dir == 'up' else 'falling' if sig_dir == 'down' else 'flat')} today, "
                    "the near-term effect is mostly on sentiment and valuation rather than immediate earnings. "
                    "Use staggered entries and size positions based on volatility."
                )

            # Pick top 2 other relevant signals by sector
            sector_low = str(sector or "").lower()
            relevance = []
            if "technology" in sector_low or base in {"TCS", "INFY"}:
                relevance = ["usd_inr", "us_10y_yield", "india_vix", "wti_crude", "gold"]
            elif "financial" in sector_low or "bank" in sector_low or base == "HDFCBANK":
                relevance = ["us_10y_yield", "india_vix", "usd_inr", "gold", "wti_crude"]
            elif "energy" in sector_low or base in {"RELIANCE", "ONGC"}:
                relevance = ["wti_crude", "usd_inr", "india_vix", "us_10y_yield", "gold"]
            else:
                relevance = ["india_vix", "usd_inr", "us_10y_yield", "wti_crude", "gold"]

            lines = [
                f"**STOCK-MACRO ANALYSIS: {clean}**",
                "",
                f"**Current Price:** {price_str}",
                f"**Sector:** {sector}",
                "",
                f"**Relevant Macro Signal: {_MACRO_LABELS.get(signal_key, signal_key)}**",
                f"**Current Value:** {sig_val} ({sig_chg})",
                "",
            ]
            lines.extend([f"**How {_MACRO_LABELS.get(signal_key, signal_key)} Affects {clean}:**", narrative, ""])

            lines.append("**Other Relevant Signals:**")
            added = 0
            for k in relevance:
                if k == signal_key:
                    continue
                line = _other_signal_line(k)
                if line:
                    lines.append(line)
                    added += 1
                if added >= 2:
                    break

            # Actionable overall view
            stance = "HOLD"
            if signal_key in {"usd_inr"} and (sig_dir == "up") and ("technology" in sector_low or base in {"TCS", "INFY"}):
                stance = "BUY (selective)"
            if signal_key in {"us_10y_yield"} and sig_dir == "up" and ("technology" in sector_low):
                stance = "AVOID / WAIT"
            if signal_key == "india_vix" and sig and isinstance(sig, dict):
                try:
                    if float(sig.get("current_value") or 0) >= 20 and float(sig.get("change_pct") or 0) > 0:
                        stance = "AVOID / REDUCE SIZE"
                except Exception:
                    pass

            lines.extend([
                "",
                "**Overall View:**",
                f"Based on the primary signal and today’s direction, the near-term stance for {clean} is **{stance}**. "
                "If signals are supportive, accumulate gradually; if adverse, wait for better entries and keep position sizes conservative.",
                "",
                f"**Data as of:** {data_timestamp}",
            ])
            return _chat_response({"source": "stock_analysis", "result": {"symbol": sym_norm_early}, "message": "\n".join(lines), "query": q}, {"last_symbol": sym_norm_early, "last_intent": "stock_analysis"})

    # Portfolio question with listed holdings but no weights -> assume equal weights (do not prompt)
    if (("my portfolio" in ql) or ("analyze portfolio" in ql) or ("analyse portfolio" in ql)) and not re.search(r"\d+\s*%", ql):
        # Resolve up to 10 explicit symbols from query tokens
        tokens = get_raw_parser_symbols(q, context=ctx)
        resolved: List[str] = []
        seen = set()
        for t in tokens:
            s = _normalize_symbol_maybe(t)
            if s and s not in seen:
                seen.add(s)
                resolved.append(s)
        if len(resolved) >= 2:
            equal = round(100.0 / len(resolved), 2)
            allocs_eq = [{"symbol": s, "weight_percent": equal} for s in resolved]
            portfolio_result = await _portfolio_allocation_analysis(allocs_eq)
            if isinstance(portfolio_result, dict) and not portfolio_result.get("error"):
                # Direction-aware macro overlay (recomputed below in allocs path too; keep here for this branch)
                macro_overlay: List[str] = []
                try:
                    from app.services.cross_market_service import get_cross_market_signals
                    sigs = get_cross_market_signals() or {}

                    # Determine portfolio composition
                    stocks = portfolio_result.get("stocks") or []
                    sectors = [str(s.get("sector") or "").lower() for s in stocks if isinstance(s, dict)]
                    has_it = any("technology" in x or "it" == x for x in sectors)
                    has_energy = any("energy" in x for x in sectors) or any(s.get("symbol") in {"ONGC.NS", "RELIANCE.NS"} for s in stocks if isinstance(s, dict))
                    has_banking = any("financial" in x or "bank" in x for x in sectors)

                    # Crude Oil overlay
                    c_cv, c_cp, c_dir = _get_sig(sigs, "wti_crude")
                    if c_cp is not None:
                        if c_dir == "up" and has_energy:
                            macro_overlay.append(f"Crude up {c_cp:+.2f}% — POSITIVE for ONGC/energy holdings. Revenue realization improves.")
                        elif c_dir == "up" and has_it and not has_energy:
                            macro_overlay.append(f"Crude up {c_cp:+.2f}% — LOW direct IT impact. Watch inflation risk indirectly.")
                        elif c_dir == "down":
                            macro_overlay.append(f"Crude down {c_cp:+.2f}% — margin relief for aviation/logistics. Energy stock revenues soften.")

                    # Bond Yield overlay
                    y_cv, y_cp, y_dir = _get_sig(sigs, "us_10y_yield")
                    if y_cp is not None:
                        if abs(y_cp) < 0.01:
                            macro_overlay.append("Yield flat — neutral, no incremental pressure.")
                        elif y_dir == "up" and has_it:
                            macro_overlay.append(f"Yield up {y_cp:+.2f}% — valuation headwind for TCS/INFY. Growth stock discount rates rise.")
                        elif y_dir == "up" and has_banking:
                            macro_overlay.append(f"Yield up {y_cp:+.2f}% — NIM expansion positive for banking holdings.")

                    # India VIX overlay
                    v_cv, v_cp, v_dir = _get_sig(sigs, "india_vix")
                    if v_cv is not None and v_cp is not None:
                        if v_cv >= 20 and v_cp > 0:
                            macro_overlay.append(f"VIX at {v_cv:.2f}, up {v_cp:+.2f}% — elevated fear. Consider reducing position sizes in volatile names.")
                        elif v_cv >= 20 and v_cp < 0:
                            macro_overlay.append(f"VIX at {v_cv:.2f}, easing — fear reducing. Cautious re-entry opportunity forming.")
                        elif v_cv < 20:
                            macro_overlay.append(f"VIX at {v_cv:.2f} — calm market. Normal position sizing appropriate.")
                except Exception:
                    pass

                msg = _format_portfolio_analysis(
                    portfolio_result.get("stocks") or [],
                    portfolio_result.get("allocations") or [],
                    portfolio_result.get("sector_breakdown") or {},
                    float(portfolio_result.get("diversification_score", 0)),
                    str(portfolio_result.get("risk_level", "Low")),
                    "Equal weights assumed (no weights provided). " + str(portfolio_result.get("suggestions", "")),
                    macro_overlay,
                )
                return _chat_response(
                    {"source": "portfolio_analysis", "result": portfolio_result, "message": msg, "query": q},
                    {"last_intent": "portfolio_analysis", "last_portfolio_allocations": allocs_eq},
                )

    # Hypothetical macro check BEFORE portfolio — never route to portfolio
    if is_hypothetical_macro_query(q):
        allocs = []
    else:
        allocs = _extract_portfolio_allocations(q)
    if allocs:
        portfolio_result = await _portfolio_allocation_analysis(allocs)
        if isinstance(portfolio_result, dict) and portfolio_result.get("error"):
            return _chat_response({"source": "portfolio_analysis", "result": portfolio_result, "query": q}, {})
        # Direction-aware Macro Risk Overlay (Live)
        macro_overlay: List[str] = []
        try:
            from app.services.cross_market_service import get_cross_market_signals
            sigs = get_cross_market_signals() or {}

            stocks = portfolio_result.get("stocks") or []
            sectors = [str(s.get("sector") or "").lower() for s in stocks if isinstance(s, dict)]
            has_it = any("technology" in x or x == "it" for x in sectors) or any(s.get("symbol", "").endswith(("TCS.NS", "INFY.NS")) for s in stocks if isinstance(s, dict))
            has_energy = any("energy" in x for x in sectors) or any(str(s.get("symbol") or "").upper() in {"ONGC.NS", "RELIANCE.NS"} for s in stocks if isinstance(s, dict))
            has_banking = any("financial" in x or "bank" in x for x in sectors)

            # Crude Oil
            c_cv, c_cp, c_dir = _get_sig(sigs, "wti_crude")
            if c_cp is not None:
                if c_dir == "up" and has_energy:
                    macro_overlay.append(f"Crude up {c_cp:+.2f}% — POSITIVE for ONGC/energy holdings. Revenue realization improves.")
                elif c_dir == "up" and has_it and not has_energy:
                    macro_overlay.append(f"Crude up {c_cp:+.2f}% — LOW direct IT impact. Watch inflation risk indirectly.")
                elif c_dir == "down":
                    macro_overlay.append(f"Crude down {c_cp:+.2f}% — margin relief for aviation/logistics. Energy stock revenues soften.")

            # Bond Yield
            y_cv, y_cp, y_dir = _get_sig(sigs, "us_10y_yield")
            if y_cp is not None:
                if abs(y_cp) < 0.01:
                    macro_overlay.append("Yield flat — neutral, no incremental pressure.")
                elif y_dir == "up" and has_it:
                    macro_overlay.append(f"Yield up {y_cp:+.2f}% — valuation headwind for TCS/INFY. Growth stock discount rates rise.")
                elif y_dir == "up" and has_banking:
                    macro_overlay.append(f"Yield up {y_cp:+.2f}% — NIM expansion positive for banking holdings.")

            # India VIX
            v_cv, v_cp, v_dir = _get_sig(sigs, "india_vix")
            if v_cv is not None and v_cp is not None:
                if v_cv >= 20 and v_cp > 0:
                    macro_overlay.append(f"VIX at {v_cv:.2f}, up {v_cp:+.2f}% — elevated fear. Consider reducing position sizes in volatile names.")
                elif v_cv >= 20 and v_cp < 0:
                    macro_overlay.append(f"VIX at {v_cv:.2f}, easing — fear reducing. Cautious re-entry opportunity forming.")
                elif v_cv < 20:
                    macro_overlay.append(f"VIX at {v_cv:.2f} — calm market. Normal position sizing appropriate.")
        except Exception:
            pass
        msg = _format_portfolio_analysis(
            portfolio_result.get("stocks") or [],
            portfolio_result.get("allocations") or [],
            portfolio_result.get("sector_breakdown") or {},
            float(portfolio_result.get("diversification_score", 0)),
            str(portfolio_result.get("risk_level", "Low")),
            str(portfolio_result.get("suggestions", "")),
            macro_overlay,
        )
        return _chat_response(
            {"source": "portfolio_analysis", "result": portfolio_result, "message": msg, "query": q},
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

    # Cross-market macro analysis (bond yields, oil, FX, gold, India VIX)
    # Standard format: MACRO SIGNAL ANALYSIS block (no raw data dump)
    if intent in {"macro_analysis", "cross_market_impact"}:
        from app.services.cross_market_service import get_cross_market_signals
        from app.services.causality_engine import interpret_causality
        from app.utils.datetime_utils import get_ist_timestamp

        data_timestamp = get_ist_timestamp()
        signals = get_cross_market_signals() or {}
        causal_insights = interpret_causality(signals) if signals else []

        sector_macro = _detect_sector_macro_query(q)
        if sector_macro:
            message = _format_sector_macro_analysis(signals, sector_macro, data_timestamp)
        elif _is_neutral_macro_education(q):
            message = _format_neutral_macro_scenario(signals, data_timestamp)
        elif _is_sector_safety_query(q):
            message = _format_sector_safety_ranking(signals, data_timestamp)
        elif _is_hypothetical_macro_question(q):
            scenario = _detect_hypothetical_scenario(q)
            if scenario:
                message = _format_hypothetical_macro_analysis(signals, q, scenario, data_timestamp)
            else:
                message = _format_macro_signal_analysis(signals, causal_insights, data_timestamp, q)
        else:
            message = _format_macro_signal_analysis(signals, causal_insights, data_timestamp, q)

        return _chat_response(
            {
                "source": "macro",
                "result": {"signals": signals, "causal_insights": causal_insights, "data_timestamp": data_timestamp},
                "message": message,
                "query": q,
            },
            {"last_intent": intent},
        )

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
            # Use dedicated comparison symbol extractor; for follow-ups with no symbols, reuse previous set.
            compare_syms = _extract_comparison_symbols_from_query(q)
            if not compare_syms:
                compare_syms = list(symbols) if symbols else []
            if not compare_syms and last_symbols:
                compare_syms = list(last_symbols)
            if len(compare_syms) < 2:
                return (
                    {
                        "message": (
                            "I couldn't identify the stocks in your message. Try:\n"
                            "• compare TCS and INFY\n"
                            "• TCS vs HDFC vs RELIANCE\n"
                            "• compare tcs infy wipro"
                        )
                    },
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
                    {
                        "message": (
                            "I couldn't identify the stocks in your message. Try:\n"
                            "• compare TCS and INFY\n"
                            "• TCS vs HDFC vs RELIANCE\n"
                            "• compare tcs infy wipro"
                        )
                    },
                    {},
                )

            # Multi-stock comparison (2+)
            multi = await _multi_comparison_result(resolved_syms[:6])
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
                    {
                        "message": (
                            "I couldn't identify the stocks in your message. Try:\n"
                            "• compare TCS and INFY\n"
                            "• TCS vs HDFC vs RELIANCE\n"
                            "• compare tcs infy wipro"
                        )
                    },
                    {},
                )

            # Build markdown table
            headers = [str(r.get("name") or r.get("symbol") or "").replace(".NS", "").replace(".BO", "") for r in rows]

            def _fmt_price_inr(x: Any) -> str:
                if isinstance(x, str) and x.startswith("Rs."):
                    return x
                try:
                    return f"Rs.{float(x):,.2f}"
                except Exception:
                    return "N/A"

            def _fmt_price_usd(x: Any) -> str:
                if isinstance(x, str) and x.startswith("$"):
                    return x
                try:
                    return f"${float(x):,.2f}"
                except Exception:
                    return "N/A"

            def _fmt_pe(x: Any) -> str:
                try:
                    return f"{float(x):.1f}"
                except Exception:
                    return "N/A"

            def _fmt_div(x: Any) -> str:
                try:
                    return f"{float(x):.2f}%"
                except Exception:
                    return "N/A"

            def format_market_cap(raw_value):
                if not raw_value:
                    return "N/A"
                crores = float(raw_value) / 10_000_000
                if crores >= 1_00_000:
                    return f"{round(crores / 1_00_000, 2)} L Cr"
                elif crores >= 1_000:
                    return f"{round(crores, 0):.0f} Cr"
                else:
                    return f"{round(crores, 2)} Cr"

            def _fmt_mc(x: Any) -> str:
                if not x or str(x).upper() == "N/A":
                    return "N/A"
                # x may be raw numeric market cap; always format to Cr/L Cr
                try:
                    return format_market_cap(float(x))
                except Exception:
                    return str(x)

            def _fmt_change(x: Any) -> str:
                try:
                    v = float(x)
                except Exception:
                    return "N/A"
                sign = "+" if v >= 0 else ""
                return f"{sign}{v:.2f}%"

            lines: List[str] = []
            header_row = "| Metric         | " + " | ".join(h for h in headers) + " |"
            sep_row = "|----------------| " + " | ".join(["------------"] * len(headers)) + " |"
            lines.append(header_row)
            lines.append(sep_row)

            def _row(metric: str, values: List[str]) -> None:
                lines.append("| " + metric.ljust(14) + " | " + " | ".join(values) + " |")

            has_commodity = any((r.get("assetType") == "Commodity") for r in rows)
            has_stock = any((r.get("assetType") != "Commodity") for r in rows)

            if has_commodity and not has_stock:
                # Pure commodity / crypto comparison: show USD and time-horizon changes.
                _row("Price (USD)", [_fmt_price_usd(r.get("price")) for r in rows])
                _row("52W High", [_fmt_price_usd(r.get("high_52w")) for r in rows])
                _row("52W Low", [_fmt_price_usd(r.get("low_52w")) for r in rows])
                _row("Today Change", [_fmt_change(r.get("todayChange")) for r in rows])
                _row("1M Change", [_fmt_change(r.get("change1m")) for r in rows])
                _row("3M Change", [_fmt_change(r.get("change3m")) for r in rows])
                _row("YTD Change", [_fmt_change(r.get("changeYtd")) for r in rows])
                _row("Asset Type", [str(r.get("assetType") or "Commodity") for r in rows])
            elif has_commodity and has_stock:
                # Mixed stocks + commodities: shared price-based metrics only.
                def _price_mixed(row: Dict[str, Any]) -> str:
                    if row.get("assetType") == "Commodity":
                        return _fmt_price_usd(row.get("price"))
                    return _fmt_price_inr(row.get("price"))

                def _price_52w_mixed(row: Dict[str, Any], key: str) -> str:
                    if row.get("assetType") == "Commodity":
                        return _fmt_price_usd(row.get(key))
                    return _fmt_price_inr(row.get(key))

                _row("Price", [_price_mixed(r) for r in rows])
                _row("52W High", [_price_52w_mixed(r, "high_52w") for r in rows])
                _row("52W Low", [_price_52w_mixed(r, "low_52w") for r in rows])
                _row("Today Change", [_fmt_change(r.get("todayChange")) for r in rows])
            else:
                # Stock-only comparison (existing behaviour).
                _row("Price", [_fmt_price_inr(r.get("price")) for r in rows])
                _row("P/E Ratio", [_fmt_pe(r.get("pe")) for r in rows])
                _row("Dividend Yield", [_fmt_div(r.get("dividendYield")) for r in rows])
                _row("Market Cap", [_fmt_mc(r.get("marketCap")) for r in rows])
                _row("52W High", [_fmt_price_inr(r.get("high_52w")) for r in rows])
                _row("52W Low", [_fmt_price_inr(r.get("low_52w")) for r in rows])
                _row("Sector", [str(r.get("sector") or "N/A") for r in rows])
                _row("Today Change", [_fmt_change(r.get("todayChange")) for r in rows])

            leaders = multi.get("leaders") or {}
            val_leader = leaders.get("valuation_leader")
            inc_leader = leaders.get("income_leader")
            size_leader = leaders.get("size_leader")
            mom_leader = leaders.get("momentum_leader")
            best_today = leaders.get("best_today")
            best_1m = leaders.get("best_1m")
            best_3m = leaders.get("best_3m")
            overall_trend_text = leaders.get("overall_trend_text")
            has_commodity = bool(multi.get("has_commodity"))
            has_stock = bool(multi.get("has_stock"))

            def _name_or_na(row: Optional[Dict[str, Any]]) -> str:
                if not isinstance(row, dict):
                    return "N/A"
                return str(row.get("name") or row.get("symbol") or "N/A").replace(".NS", "").replace(".BO", "")

            lines.append("")

            if has_commodity:
                # Commodity / mixed comparison winners
                if best_today:
                    lines.append(f"Best Performer (Today)  : {_name_or_na(best_today)}")
                else:
                    lines.append("Best Performer (Today)  : N/A")
                if best_1m:
                    lines.append(f"Best Performer (1 Month): {_name_or_na(best_1m)}")
                else:
                    lines.append("Best Performer (1 Month): N/A")
                if best_3m:
                    lines.append(f"Best Performer (3 Month): {_name_or_na(best_3m)}")
                else:
                    lines.append("Best Performer (3 Month): N/A")

                trend_text = overall_trend_text or "Macro context for commodities and related sectors looks broadly neutral based on current cross-market signals."
                lines.append(f"Overall Trend           : {trend_text}")

                if has_stock:
                    lines.append("")
                    lines.append(
                        "Note: Direct comparison between stocks and commodities is limited. Metrics shown are price-based only."
                    )
            else:
                # Stock-only winners (existing behaviour)
                lines.append(f"Valuation Winner : {_name_or_na(val_leader)}")
                lines.append(f"Income Winner    : {_name_or_na(inc_leader)}")
                lines.append(f"Size Winner      : {_name_or_na(size_leader)}")
                if mom_leader:
                    lines.append(f"Today Winner     : {_name_or_na(mom_leader)}")
                else:
                    lines.append("Today Winner     : Could not fetch intraday data")

                # Overall pick with macro-aware summary (best-effort)
                overall_pick_row = val_leader or mom_leader or size_leader or inc_leader
                overall_pick = _name_or_na(overall_pick_row)
                try:
                    from app.services.cross_market_service import get_cross_market_signals

                    sigs = get_cross_market_signals() or {}
                    us10 = sigs.get("us_10y_yield") or {}
                    vix = sigs.get("india_vix") or {}
                    parts: List[str] = []
                    if isinstance(us10, dict) and us10.get("current_value") is not None:
                        parts.append(
                            f"US 10Y bond yield is around {float(us10['current_value']):.2f}, "
                            f"{'up' if (us10.get('change_pct') or 0) > 0 else 'down' if (us10.get('change_pct') or 0) < 0 else 'flat'} "
                            f"{abs(float(us10.get('change_pct') or 0)):.2f}% today."
                        )
                    if isinstance(vix, dict) and vix.get("current_value") is not None:
                        parts.append(
                            f"India VIX is near {float(vix['current_value']):.2f}, "
                            f"indicating {'calmer' if (vix.get('change_pct') or 0) < 0 else 'elevated'} risk sentiment."
                        )
                    macro_text = (
                        " ".join(parts)
                        if parts
                        else "Macro conditions look broadly neutral; treat this as a relative comparison, not a timing signal."
                    )
                except Exception:
                    macro_text = "Macro signals are unavailable right now; treat this as a relative comparison based on valuation, income, and recent moves."

                overall_sentence_parts: List[str] = []
                if isinstance(size_leader, dict):
                    mc_disp = size_leader.get("market_cap_display") or size_leader.get("marketCap")
                    overall_sentence_parts.append(
                        f"{_name_or_na(size_leader)} leads on market cap ({mc_disp})."
                    )
                if isinstance(val_leader, dict) and isinstance(inc_leader, dict):
                    overall_sentence_parts.append(
                        f"{_name_or_na(val_leader)} looks strongest on valuation (P/E {val_leader.get('pe')}), "
                        f"while {_name_or_na(inc_leader)} offers the best income profile (yield {inc_leader.get('dividendYield')})."
                    )
                elif isinstance(val_leader, dict):
                    overall_sentence_parts.append(
                        f"{_name_or_na(val_leader)} looks strongest on valuation among the compared stocks."
                    )
                elif isinstance(inc_leader, dict):
                    overall_sentence_parts.append(
                        f"{_name_or_na(inc_leader)} offers the best income profile based on dividend yield."
                    )
                overall_sentence_parts.append(macro_text)
                overall_sentence = " ".join(overall_sentence_parts)

                lines.append(f"Overall Pick     : {overall_pick} – {overall_sentence}")

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
        if isinstance(portfolio_result, dict) and not portfolio_result.get("error"):
            macro_overlay_po: List[str] = []
            try:
                from app.services.cross_market_service import get_cross_market_signals
                sigs = get_cross_market_signals() or {}
                stocks = portfolio_result.get("stocks") or []
                sectors = [str(s.get("sector") or "").lower() for s in stocks if isinstance(s, dict)]
                has_it = any("technology" in x or x == "it" for x in sectors)
                has_energy = any("energy" in x for x in sectors) or any(str(s.get("symbol") or "").upper() in {"ONGC.NS", "RELIANCE.NS"} for s in stocks if isinstance(s, dict))
                has_banking = any("financial" in x or "bank" in x for x in sectors)

                c_cv, c_cp, c_dir = _get_sig(sigs, "wti_crude")
                if c_cp is not None:
                    if c_dir == "up" and has_energy:
                        macro_overlay_po.append(f"Crude up {c_cp:+.2f}% — POSITIVE for ONGC/energy holdings. Revenue realization improves.")
                    elif c_dir == "up" and has_it and not has_energy:
                        macro_overlay_po.append(f"Crude up {c_cp:+.2f}% — LOW direct IT impact. Watch inflation risk indirectly.")
                    elif c_dir == "down":
                        macro_overlay_po.append(f"Crude down {c_cp:+.2f}% — margin relief for aviation/logistics. Energy stock revenues soften.")

                y_cv, y_cp, y_dir = _get_sig(sigs, "us_10y_yield")
                if y_cp is not None:
                    if abs(y_cp) < 0.01:
                        macro_overlay_po.append("Yield flat — neutral, no incremental pressure.")
                    elif y_dir == "up" and has_it:
                        macro_overlay_po.append(f"Yield up {y_cp:+.2f}% — valuation headwind for TCS/INFY. Growth stock discount rates rise.")
                    elif y_dir == "up" and has_banking:
                        macro_overlay_po.append(f"Yield up {y_cp:+.2f}% — NIM expansion positive for banking holdings.")

                v_cv, v_cp, v_dir = _get_sig(sigs, "india_vix")
                if v_cv is not None and v_cp is not None:
                    if v_cv >= 20 and v_cp > 0:
                        macro_overlay_po.append(f"VIX at {v_cv:.2f}, up {v_cp:+.2f}% — elevated fear. Consider reducing position sizes in volatile names.")
                    elif v_cv >= 20 and v_cp < 0:
                        macro_overlay_po.append(f"VIX at {v_cv:.2f}, easing — fear reducing. Cautious re-entry opportunity forming.")
                    elif v_cv < 20:
                        macro_overlay_po.append(f"VIX at {v_cv:.2f} — calm market. Normal position sizing appropriate.")
            except Exception:
                pass
            msg_po = _format_portfolio_analysis(
                portfolio_result.get("stocks") or [],
                portfolio_result.get("allocations") or [],
                portfolio_result.get("sector_breakdown") or {},
                float(portfolio_result.get("diversification_score", 0)),
                str(portfolio_result.get("risk_level", "Low")),
                str(portfolio_result.get("suggestions", "")),
                macro_overlay_po,
            )
            return _chat_response(
                {"source": "portfolio_analysis", "result": portfolio_result, "message": msg_po, "query": q},
                {"last_intent": intent},
            )
        return _chat_response({"source": "portfolio_analysis", "result": portfolio_result or {}, "query": q}, {"last_intent": intent})
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
            "symbol": sym_norm,
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
            # Use same standard STOCK ANALYSIS format as buy_decision
            macro_overlay_ar: List[str] = []
            try:
                from app.services.cross_market_service import get_cross_market_signals
                sigs = get_cross_market_signals() or {}
                sector_lower = str(sector or "").lower()

                def _overlay_label(key: str, cv: float, cp: float) -> str:
                    if key == "us_10y_yield":
                        if "technology" in sector_lower or sym_norm.replace(".NS", "").upper() in {"TCS", "INFY"}:
                            return "valuation headwind" if cp > 0 else "valuation tailwind" if cp < 0 else "neutral — no pressure"
                        if "financial" in sector_lower or "bank" in sector_lower:
                            return "NIM expansion positive" if cp > 0 else "NIM compression risk" if cp < 0 else "stable margin outlook"
                        return "neutral"
                    if key == "usd_inr":
                        if "technology" in sector_lower or sym_norm.replace(".NS", "").upper() in {"TCS", "INFY"}:
                            return "export revenue tailwind" if cp > 0 else "export revenue headwind" if cp < 0 else "neutral"
                        return "low direct impact"
                    if key == "india_vix":
                        if cv >= 20 and cp > 0:
                            return "elevated fear — reduce size"
                        if cv >= 20 and cp < 0:
                            return "fear easing — cautious entry"
                        return "calm market — normal sizing"
                    return "neutral"

                for key, label in [("us_10y_yield", "Bond Yield"), ("usd_inr", "USD/INR"), ("india_vix", "India VIX")]:
                    s = sigs.get(key) if isinstance(sigs, dict) else None
                    if s and isinstance(s, dict) and s.get("current_value") is not None:
                        cv = float(s.get("current_value"))
                        cp = float(s.get("change_pct") or 0)
                        hint = _overlay_label(key, cv, cp)
                        macro_overlay_ar.append(f"{label} {cv:.2f} ({cp:+.2f}%) — {hint}")
            except Exception:
                pass
            div_yield_ar = detail.get("dividendYield") or detail.get("div_yield")
            if div_yield_ar is not None:
                try:
                    div_yield_ar = f"{float(div_yield_ar) * 100:.2f}" if float(div_yield_ar) < 1 else f"{float(div_yield_ar):.2f}"
                except Exception:
                    div_yield_ar = "N/A"
            msg_ar = _format_stock_buy_analysis(
                sym_norm, final_rec, final_score_100, price, pe, sector, sector_avg_pe,
                div_yield_ar, int(round(mom_f * 100)), int(round(pred_f * 100)), mr_label,
                macro_overlay_ar, conclusion_text,
            )
            return _chat_response(
                {"source": "buy_recommendation", "result": result, "message": msg_ar, "query": q},
                {"last_symbol": sym_norm, "last_intent": "buy_recommendation"},
            )

        # buy_decision: standard STOCK ANALYSIS format with macro overlay
        macro_overlay: List[str] = []
        try:
            from app.services.cross_market_service import get_cross_market_signals
            sigs = get_cross_market_signals() or {}
            sector_lower = str(sector or "").lower()

            def _overlay_label(key: str, cv: float, cp: float) -> str:
                if key == "us_10y_yield":
                    if "technology" in sector_lower or sym_norm.replace(".NS", "").upper() in {"TCS", "INFY"}:
                        return "valuation headwind" if cp > 0 else "valuation tailwind" if cp < 0 else "neutral — no pressure"
                    if "financial" in sector_lower or "bank" in sector_lower:
                        return "NIM expansion positive" if cp > 0 else "NIM compression risk" if cp < 0 else "stable margin outlook"
                    return "neutral"
                if key == "usd_inr":
                    if "technology" in sector_lower or sym_norm.replace(".NS", "").upper() in {"TCS", "INFY"}:
                        return "export revenue tailwind" if cp > 0 else "export revenue headwind" if cp < 0 else "neutral"
                    return "low direct impact"
                if key == "india_vix":
                    if cv >= 20 and cp > 0:
                        return "elevated fear — reduce size"
                    if cv >= 20 and cp < 0:
                        return "fear easing — cautious entry"
                    return "calm market — normal sizing"
                return "neutral"

            for key, label in [("us_10y_yield", "Bond Yield"), ("usd_inr", "USD/INR"), ("india_vix", "India VIX")]:
                s = sigs.get(key) if isinstance(sigs, dict) else None
                if s and isinstance(s, dict) and s.get("current_value") is not None:
                    cv = float(s.get("current_value"))
                    cp = float(s.get("change_pct") or 0)
                    hint = _overlay_label(key, cv, cp)
                    macro_overlay.append(f"{label} {cv:.2f} ({cp:+.2f}%) — {hint}")
        except Exception:
            pass
        div_yield = detail.get("dividendYield") or detail.get("div_yield")
        if div_yield is not None:
            try:
                div_yield = f"{float(div_yield) * 100:.2f}" if float(div_yield) < 1 else f"{float(div_yield):.2f}"
            except Exception:
                div_yield = "N/A"
        conclusion = f"{interpretation_text} {risk_factors_text}"
        message = _format_stock_buy_analysis(
            sym_norm,
            final_rec,
            final_score_100,
            price,
            pe,
            sector,
            sector_avg_pe,
            div_yield,
            int(round(mom_f * 100)),
            int(round(pred_f * 100)),
            mr_label,
            macro_overlay,
            conclusion,
        )
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

