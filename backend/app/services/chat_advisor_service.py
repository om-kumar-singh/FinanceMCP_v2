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

from app.services.chat_intent_classifier import classify_intent, has_finance_signal
from app.services.mock_data import sample_mock_news
from app.services.news_service import get_market_news
from app.services.stock_search_service import resolve_symbol

logger = logging.getLogger(__name__)


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
            {"message": "Ask me about stock analysis, RSI/MACD, comparisons, portfolio risk, market news, or macro data."},
            {},
        )

    # Portfolio allocation detection (highest priority when user pastes weights)
    allocs = _extract_portfolio_allocations(q)
    if allocs:
        portfolio_result = await _portfolio_allocation_analysis(allocs)
        if isinstance(portfolio_result, dict) and portfolio_result.get("error"):
            return ({"source": "portfolio_analysis", "result": portfolio_result, "query": q}, {})
        return (
            {"source": "portfolio_analysis", "result": portfolio_result, "query": q},
            {"last_intent": "portfolio_analysis", "last_portfolio_allocations": allocs},
        )

    classified = classify_intent(q, context=ctx)
    intent = classified.intent
    symbols = classified.symbols
    primary_symbol = classified.primary_symbol
    indicator_type = classified.indicator_type

    # Normalize primary symbol to yfinance form if possible
    primary_symbol = _normalize_symbol_maybe(primary_symbol) if primary_symbol else None

    # Pull previous context
    last_symbols = ctx.get("last_symbols") if isinstance(ctx.get("last_symbols"), list) else None
    last_portfolio_allocs = ctx.get("last_portfolio_allocations") if isinstance(ctx.get("last_portfolio_allocations"), list) else None

    # ---- Routing ----

    # comparison
    if intent == "comparison":
        # For follow-ups like "which is better?" reuse previous compare pair.
        compare_syms = symbols
        if len(compare_syms) < 2 and last_symbols:
            compare_syms = list(last_symbols)[:2]
        if len(compare_syms) < 2:
            return (
                {"message": "Which two stocks should I compare? Example: `Compare TCS and INFY`."},
                {},
            )
        comp = await _comparison_result(compare_syms[:2])
        if comp:
            return (
                {"source": "compare_stocks", "result": comp, "query": q},
                {"last_symbols": [comp.get("symbol1"), comp.get("symbol2")], "last_symbol": comp.get("symbol1"), "last_intent": "comparison"},
            )
        return ({"source": "compare_stocks", "result": {"error": "Unable to fetch comparison data"}, "query": q}, {"last_intent": "comparison"})

    # Technical indicators
    if intent == "technical_indicator":
        sym = primary_symbol or (ctx.get("last_symbol") if isinstance(ctx.get("last_symbol"), str) else None)
        sym = _normalize_symbol_maybe(sym) if sym else None
        if not sym:
            return ({"message": "Which stock should I run indicators for? Example: `What does RSI say about INFY?`"}, {})

        from app.services.stock_service import calculate_macd, calculate_moving_averages, calculate_rsi

        if indicator_type == "rsi":
            r = await _run_sync_with_timeout(calculate_rsi, sym, timeout_s=10.0)
            return ({"source": "rsi", "result": r or {"error": "No RSI data"}, "query": q}, {"last_symbol": sym, "last_intent": "technical_indicator"})
        if indicator_type == "macd":
            r = await _run_sync_with_timeout(calculate_macd, sym, timeout_s=10.0)
            return ({"source": "macd", "result": r or {"error": "No MACD data"}, "query": q}, {"last_symbol": sym, "last_intent": "technical_indicator"})
        if indicator_type == "moving_averages":
            r = await _run_sync_with_timeout(calculate_moving_averages, sym, timeout_s=10.0)
            return ({"source": "moving_averages", "result": r or {"error": "No moving averages data"}, "query": q}, {"last_symbol": sym, "last_intent": "technical_indicator"})

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

        return (
            {
                "source": "technical_analysis",
                "result": {"symbol": sym, "rsi": rsi if isinstance(rsi, dict) and not rsi.get("error") else None, "macd": macd if isinstance(macd, dict) and not macd.get("error") else None, "moving_averages": ma if isinstance(ma, dict) and not ma.get("error") else None, "interpretation": interp},
                "query": q,
            },
            {"last_symbol": sym, "last_intent": "technical_indicator"},
        )

    # Market news
    if intent == "market_news":
        market = "BSE" if "bse" in q.lower() or "sensex" in q.lower() else "NSE"
        items = await _run_sync_with_timeout(get_market_news, market, timeout_s=10.0)
        if not items:
            mock = sample_mock_news(market=market, k=5)
            return (
                {"source": "market_news", "result": {"news": mock["news"], "market": market, "summary": mock["summary"]}, "query": q},
                {"last_intent": "market_news"},
            )
        return (
            {"source": "market_news", "result": {"news": items, "market": market}, "query": q},
            {"last_intent": "market_news"},
        )

    # Macro / fallback finance
    if intent == "macro_economics":
        from app.services.macro_service import get_gdp, get_inflation, get_repo_rate

        low = q.lower()
        if "repo" in low or "rbi" in low:
            r = await _run_sync_with_timeout(get_repo_rate, timeout_s=10.0)
            return ({"source": "macro", "result": r or {"error": "Unable to fetch repo rate"}, "query": q}, {})
        if "inflation" in low:
            r = await _run_sync_with_timeout(get_inflation, timeout_s=10.0)
            return ({"source": "macro", "result": r or {"error": "Unable to fetch inflation data"}, "query": q}, {})
        if "gdp" in low:
            r = await _run_sync_with_timeout(get_gdp, timeout_s=10.0)
            return ({"source": "macro", "result": r or {"error": "Unable to fetch GDP data"}, "query": q}, {})
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
        result = {"regime": regime, "top_sectors": (sectors or [])[:5]}
        return ({"source": "market_regime", "result": result, "query": q}, {"last_intent": "market_regime"})

    # Volume / smart money
    if intent == "volume_analysis":
        from app.services.advisor_v4.smart_money_tracker import detect_smart_money
        from app.services.stock_service import NIFTY_50_SYMBOLS

        sym = primary_symbol
        if sym:
            sm = await _run_sync_with_timeout(detect_smart_money, sym, timeout_s=10.0)
            return ({"source": "volume_analysis", "result": {"symbol": sym, "smart_money": sm}, "query": q}, {"last_symbol": sym, "last_intent": "volume_analysis"})

        # Screener mode: return top unusual-volume names from a small subset to stay fast.
        sample = NIFTY_50_SYMBOLS[:12]
        rows = []
        for s in sample:
            sm = await _run_sync_with_timeout(detect_smart_money, s, timeout_s=4.0)
            if isinstance(sm, dict) and sm.get("volume_zscore") is not None:
                rows.append({"symbol": s, **sm})
        rows.sort(key=lambda r: float(r.get("volume_zscore") or 0), reverse=True)
        return (
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
        predicted_price = None
        try:
            if isinstance(forecast, dict) and isinstance(quote, dict):
                er = forecast.get("expected_return")
                px = quote.get("price")
                if isinstance(er, (int, float)) and isinstance(px, (int, float)):
                    predicted_price = round(float(px) * (1.0 + float(er)), 2)
        except Exception:
            predicted_price = None

        return (
            {"source": "prediction", "result": {"symbol": sym, "quote": quote, "forecast": forecast, "predicted_price": predicted_price}, "query": q},
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

        return (
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
    if intent == "portfolio_analysis" and last_portfolio_allocs:
        portfolio_result = await _portfolio_allocation_analysis(last_portfolio_allocs)
        return ({"source": "portfolio_analysis", "result": portfolio_result, "query": q}, {"last_intent": "portfolio_analysis"})
    if intent == "portfolio_analysis":
        return (
            {"message": "Paste your portfolio weights like:\nReliance 40%\nTCS 30%\nHDFC Bank 30%\n…and I’ll analyze risk + diversification."},
            {"last_intent": "portfolio_analysis"},
        )

    # Stock analysis / advisor recommendation
    sym = primary_symbol or (ctx.get("last_symbol") if isinstance(ctx.get("last_symbol"), str) else None)
    sym_norm = _normalize_symbol_maybe(sym) if sym else None
    if sym_norm and intent == "advisor_recommendation":
        from app.services.advisor_v3.reasoning_engine import analyse_symbol_v3
        from app.services.stock_service import get_stock_detail

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
        recommendation = None
        if isinstance(v3, dict) and v3.get("recommendation"):
            recommendation = str(v3.get("recommendation")).lower()
            interpretation = v3.get("explanation")

        result = {
            "symbol": sym_norm,
            "price": price,
            "pe": pe,
            "sector": sector,
            "sector_avg_pe": sector_avg_pe,
            "interpretation": interpretation or "I could not generate a full reasoning trace right now; showing live metrics instead.",
            "risk_factors": "Sector and macro risks apply; use position sizing and risk controls.",
            "conclusion": "Use this as decision support, not financial advice.",
        }
        return (
            {"source": "buy_recommendation", "result": result, "query": q},
            {"last_symbol": sym_norm, "last_intent": "buy_recommendation"},
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
            return (
                {
                    "source": "stock_analysis",
                    "result": {
                        "title": f"Stock Analysis: {name}",
                        "symbol": detail.get("symbol") or sym_norm,
                        "price": detail.get("price"),
                        "pe": pe,
                        "dividendYield": detail.get("dividendYield", 0),
                        "marketCap": detail.get("marketCap"),
                        "sector": sector,
                        "sector_avg_pe": sector_avg_pe,
                        "interpretation": interp,
                        "risk_factors": "Sector and market risks apply; do your own research.",
                    },
                    "query": q,
                },
                {"last_symbol": detail.get("symbol") or sym_norm, "last_intent": "stock_analysis"},
            )

    # Momentum / strong picks (map to existing market_trend UI renderer)
    if any(x in q.lower() for x in ("strong momentum", "momentum", "top gainers", "which stocks have strong momentum")):
        from app.services.stock_service import get_top_gainers_losers

        r = await _run_sync_with_timeout(get_top_gainers_losers, 5, timeout_s=10.0)
        if r:
            return ({"source": "market_trend", "result": r, "query": q}, {"last_intent": "market_trend"})

    # Reduced fallback: if we saw finance signals, ask a targeted clarification instead of generic help.
    if has_finance_signal(q) or primary_symbol:
        if not primary_symbol and intent in {"advisor_recommendation", "technical_indicator", "prediction", "stock_analysis"}:
            return ({"message": "Which stock symbol/company should I use? Example: `Should I buy RELIANCE?`"}, {})
        return ({"message": "Can you clarify what you want: price/RSI/MACD, comparison, prediction, portfolio risk, or market regime?"}, {})

    return ({"message": "Tell me what you want to do (e.g., compare two stocks, run RSI, show news, or analyze a portfolio)."}, {"last_intent": "fallback"})

