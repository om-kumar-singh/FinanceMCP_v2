"""
Advisor V5 conversational API routes.

Adds:
- POST /advisor/chat
- GET  /advisor/insights  (optional AI insight feed)

These endpoints are additive and do not modify existing behaviour.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field, conlist, confloat

from app.services.advisor_v4.quant_engine import quant_analyse
from app.services.advisor_v5.financial_reasoner import reason_about_query
from app.services.advisor_v5.insight_engine import generate_insights
from app.services.advisor_v5.query_parser import parse_query
from app.services.advisor_v5.report_generator import (
    build_market_outlook_report,
    build_portfolio_report,
    build_stock_report,
)
from app.services.advisor_v5.response_generator import build_chat_response


advisor_v5_router = APIRouter(prefix="/advisor", tags=["advisor_v5"])


class PortfolioStock(BaseModel):
    symbol: str = Field(..., description="NSE/BSE symbol, e.g. RELIANCE.NS")
    quantity: confloat(gt=0) = Field(..., description="Number of shares/units held.")
    buy_price: confloat(gt=0) = Field(..., description="Average buy price per share/unit.")


def _portfolio_stocks_list_type():
    """
    Pydantic v1/v2 compatibility:
    - v1: conlist(..., min_items=..., max_items=...)
    - v2: conlist(..., min_length=..., max_length=...)
    """
    try:
        return conlist(PortfolioStock, min_length=1, max_length=50)  # type: ignore[call-arg]
    except TypeError:
        return conlist(PortfolioStock, min_items=1, max_items=50)  # type: ignore[call-arg]


PortfolioStocksList = _portfolio_stocks_list_type()


class AdvisorChatRequest(BaseModel):
    query: str = Field(..., description="Natural language financial question.")
    portfolio: Optional[PortfolioStocksList] = Field(
        None,
        description="Optional portfolio context for risk/optimization questions.",
    )
    context: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional conversational context from the caller (e.g. last_symbol).",
    )


@advisor_v5_router.post(
    "/chat",
    summary="Advisor V5 – Conversational financial assistant",
    response_description="ChatGPT-style natural language response using Advisor V1–V4 analytics.",
)
def advisor_v5_chat(payload: AdvisorChatRequest) -> Dict[str, Any]:
    """
    Conversational endpoint for financial Q&A.

    Input:
    {
      "query": "Should I buy Reliance right now?",
      "portfolio": [...],     // optional
      "context": {...}        // optional
    }

    Output:
    {
      "source": "advisor_v5",
      "response": "<natural language answer>",
      "analytics": {
        "intent": "...",
        "parsed": {...},
        "analysis": {...},
        "insights": [...]
      }
    }
    """
    import concurrent.futures
    import datetime as _dt

    q_lower = (payload.query or "").lower()

    def _fallback_response(kind: str) -> Dict[str, Any]:
        if kind == "macro":
            msg = "I was unable to fetch live macro data at this moment. Please try again in a few seconds."
        elif kind == "comparison":
            msg = "Stock data fetch timed out for one or more symbols. Please try again or check the ticker symbols."
        else:
            msg = "The request took too long. Please try again."
        return {
            "source": "advisor_v5",
            "response": msg,
            "analytics": {"intent": None, "parsed": {}, "analysis": {}, "insights": []},
        }

    def _guess_fallback_kind() -> str:
        macro_keywords = [
            "bond yield",
            "yields",
            "crude",
            "oil",
            "gold",
            "vix",
            "usd/inr",
            "rupee",
            "macro",
            "inflation",
            "interest rate",
            "currency",
        ]
        compare_keywords = ["compare", " vs ", "versus", "v/s", "vc", "vd", " and "]
        if any(k in q_lower for k in macro_keywords):
            return "macro"
        if any(k in q_lower for k in compare_keywords):
            return "comparison"
        return "general"

    MACRO_KEYWORDS = [
        "bond",
        "yield",
        "crude",
        "oil",
        "gold",
        "vix",
        "rupee",
        "usd",
        "inr",
        "macro",
        "inflation",
        "interest rate",
        "export",
        "import",
        "rbi",
        "rate",
        "currency",
        "commodity",
        "market signal",
    ]

    def _is_macro_question(msg: str) -> bool:
        m = (msg or "").lower()
        return any(kw in m for kw in MACRO_KEYWORDS)

    def fetch_single_signal(ticker_key, ticker_symbol):
        try:
            from app.utils.yfinance_wrapper import fetch_history

            hist = fetch_history(ticker_symbol, period="2d", ttl=60)
            if hist is None or getattr(hist, "empty", True):
                return ticker_key, None
            curr = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else curr
            chg = round(((curr - prev) / prev) * 100, 4) if prev else 0.0
            return (
                ticker_key,
                {
                    "current_value": round(curr, 2),
                    "previous_value": round(prev, 2),
                    "change_pct": chg,
                    "direction": "up" if chg >= 0 else "down",
                },
            )
        except Exception:
            return ticker_key, None

    TICKERS = {
        "bond_yield": "^TNX",
        "crude_oil": "CL=F",
        "usd_inr": "USDINR=X",
        "gold": "GC=F",
        "india_vix": "^INDIAVIX",
    }

    def get_cross_market_signals_fast():
        signals_out: Dict[str, Any] = {}
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
                futures = {ex.submit(fetch_single_signal, k, v): k for k, v in TICKERS.items()}
                for future in concurrent.futures.as_completed(futures, timeout=6):
                    key, result = future.result()
                    signals_out[key] = result
        except Exception:
            pass
        return signals_out

    def fetch_signals_with_timeout():
        try:
            from app.services.causality_engine import interpret_causality

            with concurrent.futures.ThreadPoolExecutor() as executor:
                # Parallelized macro fetch
                future = executor.submit(get_cross_market_signals_fast)
                sigs = future.result(timeout=5)  # 5 second max
                # Map fast keys -> causality engine expected keys (best-effort)
                mapped = {
                    "us_10y_yield": (sigs or {}).get("bond_yield"),
                    "wti_crude": (sigs or {}).get("crude_oil"),
                    "usd_inr": (sigs or {}).get("usd_inr"),
                    "gold": (sigs or {}).get("gold"),
                    "india_vix": (sigs or {}).get("india_vix"),
                }
                ins = interpret_causality(mapped) if mapped else []
                return sigs or {}, ins or []
        except Exception:
            return {}, []

    def _build_cross_market_context(signals: Dict[str, Any], causal_insights: List[Dict[str, Any]]) -> str:
        if not signals or not isinstance(signals, dict):
            return ""

        from app.utils.datetime_utils import get_ist_timestamp
        data_timestamp = get_ist_timestamp()

        def _fmt_line(label: str, key: str) -> str:
            s = signals.get(key)
            if not isinstance(s, dict):
                return f"- {label}: null"
            cv = s.get("current_value")
            cp = s.get("change_pct")
            d = s.get("direction")
            return f"- {label}: {cv} ({cp}%, {d})"

        lines = [
            f"LIVE CROSS-MARKET SIGNALS (as of {data_timestamp}):",
            _fmt_line("US 10Y Bond Yield", "bond_yield"),
            _fmt_line("Crude Oil", "crude_oil"),
            _fmt_line("USD/INR", "usd_inr"),
            _fmt_line("Gold", "gold"),
            _fmt_line("India VIX", "india_vix"),
            "",
            "CAUSAL INSIGHTS DETECTED:",
        ]

        if causal_insights:
            for ins in causal_insights:
                impact = ins.get("impact")
                severity = ins.get("severity")
                sectors = ins.get("affected_sectors")
                lines.append(f"- {impact} [Severity: {severity}] [Sectors: {sectors}]")
        else:
            lines.append("No significant causal signals detected.")

        ctx = "\n".join(lines).strip() + "\n\n"
        if len(ctx) > 400:
            ctx = ctx[:400] + "..."
        return ctx

    def _run_with_global_timeout() -> Dict[str, Any]:
        print("[ADVISOR] Step 1: Fetching cross-market signals...")
        if _is_macro_question(payload.query):
            signals, causal_insights = fetch_signals_with_timeout()
        else:
            signals, causal_insights = {}, []

        print("[ADVISOR] Step 2: Signals fetched, building context...")
        cross_market_context = _build_cross_market_context(signals, causal_insights)

        portfolio_dicts: Optional[List[Dict[str, Any]]] = None
        if payload.portfolio:
            portfolio_dicts = [
                {"symbol": p.symbol, "quantity": p.quantity, "buy_price": p.buy_price}
                for p in payload.portfolio
            ]

        print("[ADVISOR] Step 3: Detecting intent...")
        parsed = parse_query(payload.query, context=payload.context or {})
        analysis = reason_about_query(parsed, portfolio=portfolio_dicts)

        stock_report = None
        portfolio_report = None
        market_report = None

        # Attach V4 quant block if we have a primary symbol, to enrich reports/insights.
        primary_symbol = analysis.get("symbol") or parsed.get("primary_symbol")
        if primary_symbol:
            quant_block = quant_analyse(primary_symbol, portfolio=portfolio_dicts)
        else:
            quant_block = None

        if primary_symbol and quant_block:
            v3 = quant_block.get("advisor_v3") or analysis.get("advisor_v3", {})
            stock_report = build_stock_report(primary_symbol, v3, quant_block)

        if analysis.get("portfolio_optimizer") and analysis.get("portfolio_risk"):
            portfolio_report = build_portfolio_report(
                {"optimizer": analysis["portfolio_optimizer"]},
                analysis["portfolio_risk"],
            )
        elif quant_block and quant_block.get("portfolio"):
            portfolio_report = build_portfolio_report(
                quant_block["portfolio"],
                quant_block.get("risk") or {},
            )

        regime_block = analysis.get("market_regime")
        if regime_block:
            market_report = build_market_outlook_report(regime_block)

        insights = generate_insights({**analysis, "advisor_v4": quant_block} if quant_block else analysis)

        print("[ADVISOR] Step 4: Calling AI model...")
        # build_chat_response may call the LLM; enforce an upper bound so chat never hangs indefinitely.
        input_text = f"{cross_market_context}{payload.query}"
        if len(input_text) > 1200:
            # Preserve the user's query as much as possible; trim from the left.
            input_text = input_text[-1200:]
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                build_chat_response,
                input_text,
                parsed,
                {**analysis, "advisor_v4": quant_block} if quant_block else analysis,
                stock_report,
                portfolio_report,
                market_report,
                insights,
            )
            response_text = future.result(timeout=25)

        print("[ADVISOR] Step 5: Returning response...")
        return {
            "source": "advisor_v5",
            "response": response_text,
            "analytics": {
                "intent": parsed.get("intent"),
                "parsed": parsed,
                "analysis": analysis,
                "insights": insights,
            },
        }

    # Global request timeout: return within 35 seconds, always.
    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(_run_with_global_timeout)
            return future.result(timeout=35)
    except concurrent.futures.TimeoutError:
        return _fallback_response(_guess_fallback_kind())
    except Exception as e:
        # Never hang; always return a meaningful fallback.
        kind = _guess_fallback_kind()
        if kind == "macro":
            return _fallback_response("macro")
        if kind == "comparison":
            return _fallback_response("comparison")
        return {
            "source": "advisor_v5",
            "response": f"An error occurred: {str(e)}. Please try again.",
            "analytics": {"intent": None, "parsed": {}, "analysis": {}, "insights": []},
        }

    # (All logic now handled inside the global-timeout wrapper above.)


@advisor_v5_router.get(
    "/insights",
    summary="Advisor V5 – AI insight feed",
    response_description="High-level AI insights suitable for dashboard panels.",
)
def advisor_v5_insights() -> Dict[str, Any]:
    """
    Lightweight insight feed for dashboards.

    Uses a default symbol (e.g. NIFTY proxy via RELIANCE.NS) and no
    portfolio to generate generic insights.
    """
    # For now, reuse quant_analyse on a liquid large-cap as a proxy.
    symbol = "RELIANCE.NS"
    quant_block = quant_analyse(symbol, portfolio=None)
    v3 = quant_block.get("advisor_v3")
    merged = {"advisor_v3": v3, "advisor_v4": quant_block, "market_regime": quant_block.get("market_regime")}
    insights = generate_insights(merged)
    return {
        "source": "advisor_v5",
        "symbol": symbol,
        "insights": insights,
        "quant_snapshot": quant_block,
    }

