"""
Natural-language response generator for Advisor V5.

Converts structured analysis + reports + insights into a conversational
assistant-style answer. Ensures chat never returns raw JSON.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Horizon display labels
_HORIZON_LABELS = {"intraday": "1-day", "short": "5-day", "medium": "20-day"}


def _hl(horizon: str) -> str:
    return _HORIZON_LABELS.get((horizon or "short").lower(), "5-day")


# Sources that have no frontend handler in Chat.jsx - when we omit result,
# the frontend uses message instead of falling through to JSON.stringify.
_SOURCES_WITHOUT_FRONTEND_HANDLER = frozenset(
    {
        "prediction",
        "ai_picks",
        "market_regime",
        "volume_analysis",
        "investment_advice",
        "buy_recommendation",
        "rsi",
        "macd",
        "moving_averages",
        "compare_stocks",
    }
)


def format_advisor_output(result: Any) -> str:
    """
    Global formatter that guarantees readable advisor output.

    - Strings are returned as-is.
    - Dicts are converted to human text (comparison tables, regime summaries, or generic key/value lists).
    - Other types are stringified.
    """
    from typing import cast

    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        # Reuse the existing formatter logic by treating this as a bare result payload.
        try:
            return format_result_for_chat({"result": cast(Dict[str, Any], result), "source": "", "query": ""})
        except Exception:
            return "The advisor generated results but they could not be formatted."
    try:
        return str(result)
    except Exception:
        return "The advisor generated results but they could not be formatted."


def _format_multi_comparison_for_chat(result: Dict[str, Any]) -> str:
    """
    Render multi-stock comparison JSON (rows + leaders + interpretation + conclusion)
    into a readable text table plus bullets.
    """
    rows = result.get("rows") or []

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
            return f"{float(x):.2f}%"
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

    interp = result.get("interpretation") or []
    if interp:
        lines.append("")
        lines.append("Interpretation")
        for x in interp:
            lines.append(f"• {x}")

    leaders = result.get("leaders") or {}
    val = leaders.get("valuation_leader") or {}
    inc = leaders.get("income_leader") or {}
    size = leaders.get("size_leader") or {}

    if val or inc or size:
        lines.append("")
        lines.append("Conclusion")
        if val:
            lines.append(f"Valuation leader \u2192 {val.get('name')}")
        if inc:
            lines.append(f"Income leader \u2192 {inc.get('name')}")
        if size:
            lines.append(f"Size leader \u2192 {size.get('name')}")

    return "\n".join(lines)


def build_chat_response(result_or_payload, parsed=None, analysis=None, **kwargs) -> str:
    """
    Format structured result for chat display. Returns formatted text, never raw JSON.

    Two call patterns:
    - build_chat_response(payload): payload dict with source/result/query (chat_advisor_service)
    - build_chat_response(query, parsed, analysis, ...): legacy advisor_v5_routes
    """
    if parsed is not None and analysis is not None:
        return _build_chat_response_legacy(result_or_payload, parsed, analysis, **kwargs)
    try:
        if isinstance(result_or_payload, dict) and "result" in result_or_payload:
            return format_result_for_chat(result_or_payload)
        return format_result_for_chat({"result": result_or_payload, "source": "", "query": ""})
    except Exception:
        return str(result_or_payload) if result_or_payload is not None else "No data available."


def format_result_for_chat(response: Dict[str, Any]) -> str:
    """
    Convert structured JSON result into readable advisor text.
    Detects response type from "analysis" field or source.
    Never returns raw JSON.
    """
    result = response.get("result")
    source = response.get("source", "")
    if not result:
        return response.get("message", "No data available.")

    # Already have a clean message
    msg = response.get("message")
    if isinstance(msg, str) and msg and "{" not in msg and '"' not in msg[:20]:
        return msg

    analysis = result.get("analysis", "")

    # Generic multi-stock comparison (rows + leaders shape)
    if isinstance(result, dict) and isinstance(result.get("rows"), list) and result.get("rows"):
        try:
            return _format_multi_comparison_for_chat(result)
        except Exception:
            # Fall back to any plain message or generic notice if formatting fails
            msg = response.get("message")
            if isinstance(msg, str) and msg:
                return msg
            return "Comparison results generated but could not be formatted."

    # Prediction Summary
    if analysis == "Prediction Summary":
        m = result.get("metrics") or {}
        sym = (m.get("symbol") or "").replace(".NS", "").replace(".BO", "")
        hl = _hl(m.get("horizon") or m.get("horizon_label"))
        lines = [f"Prediction Summary – {sym}", ""]
        cp = m.get("current_price")
        if cp is not None:
            lines.append(f"Current Price: ₹{cp:,.2f}")
        pp = m.get("predicted_price")
        if pp is not None:
            lines.append(f"Predicted Price ({hl} forecast): ₹{pp:,.2f}")
        er = m.get("expected_return")
        if er is not None:
            pct = float(er) * 100
            lines.append(f"Expected Return: {pct:+.2f}%")
        lines.append(f"Risk Level: {m.get('risk_level', 'N/A')}")
        lines.append(f"Confidence: {m.get('confidence_label', 'N/A')}")
        lines.extend(["", "Interpretation:", result.get("interpretation", ""), "", "Risk Factors:", result.get("risk_factors", ""), "", "Conclusion:", result.get("conclusion", "")])
        return "\n".join(lines)

    # Advisor Recommendation
    if analysis == "Advisor Recommendation":
        m = result.get("metrics") or {}
        sym = (m.get("symbol") or "").replace(".NS", "").replace(".BO", "")
        comp = m.get("score_components") or {}
        fs = m.get("final_score", 0)
        rec = "BUY" if fs >= 60 else "SELL" if fs <= 40 else "HOLD"

        price = m.get("price")
        pe = m.get("pe")
        sector = m.get("sector", "N/A")

        lines: List[str] = [f"Advisor Recommendation – {sym}", ""]
        if price is not None:
            lines.append(f"Price: ₹{price:,.2f}")
        lines.append(f"PE Ratio: {pe if pe is not None else 'N/A'}")
        lines.append(f"Sector: {sector}")

        lines.extend(["", "Score Breakdown", ""])
        # Map known components explicitly to friendly labels
        def _score(val: Any) -> int:
            try:
                return int(round(float(val or 0) * 100))
            except Exception:
                return 0

        lines.append(f"Prediction: {_score(comp.get('prediction'))}")
        lines.append(f"Momentum: {_score(comp.get('momentum'))}")
        lines.append(f"Sentiment: {_score(comp.get('sentiment'))}")
        lines.append(f"Volatility Adjustment: {_score(comp.get('volatility_adjustment') or comp.get('volatility'))}")

        lines.extend(
            [
                "",
                f"Final Score: {fs} / 100",
                "",
                f"Recommendation: {rec}",
                "",
                "Interpretation:",
                result.get("interpretation", ""),
                "",
                "Risk Factors:",
                result.get("risk_factors", ""),
                "",
                "Conclusion:",
                result.get("conclusion", ""),
            ]
        )
        return "\n".join(lines)

    # Market Regime Overview
    if analysis == "Market Regime Overview":
        m = result.get("metrics") or {}
        regime = m.get("regime") or {}
        mr = regime.get("market_regime", "N/A")
        ts = regime.get("trend_strength", "N/A")
        vl = regime.get("volatility_level", "N/A")
        ret50 = regime.get("index_return_50d")
        lines = ["Market Regime Overview", "", f"Market Regime: {str(mr).replace('_', ' ').title()}", f"Trend Strength: {ts}", f"Volatility Level: {vl}"]
        if ret50 is not None:
            lines.append(f"Recent Market Return (50d): {float(ret50)*100:+.2f}%")
        top = m.get("top_sectors") or []
        if top:
            lines.extend(["", "Top Sector Signals:"])
            for s in top[:5]:
                sn = s.get("sector_name", "N/A")
                sent = s.get("sentiment", "Neutral")
                lines.append(f"  {sn} → {sent}")
        lines.extend(["", "Interpretation:", result.get("interpretation", ""), "", "Conclusion:", result.get("conclusion", "")])
        return "\n".join(lines)

    # AI Picks by Predicted Growth
    if analysis == "AI Picks by Predicted Growth":
        m = result.get("metrics") or {}
        ranked = m.get("ranked") or []
        hl = _hl(m.get("horizon") or m.get("horizon_label"))
        lines = [f"Top AI Picks ({hl} forecast)", ""]
        for i, row in enumerate(ranked[:10], 1):
            sym = (row.get("symbol") or "").replace(".NS", "").replace(".BO", "")
            er = row.get("expected_return")
            if er is not None:
                pct = float(er) * 100
                pct_str = "~0%" if abs(pct) < 0.2 else f"{pct:+.1f}%"
            else:
                pct_str = "N/A"
            lines.append(f"{i}. {sym} → {pct_str}")
        return "\n".join(lines)

    # Stock Analysis
    if analysis or "Stock Analysis" in str(result.get("title", "")):
        title = result.get("title") or result.get("symbol") or "Stock"
        sym = str(title).replace(".NS", "").replace(".BO", "")
        if "Stock Analysis" in str(title):
            name = sym.replace("Stock Analysis: ", "")
        else:
            name = (result.get("symbol") or sym).replace(".NS", "").replace(".BO", "")
        lines = [f"Stock Analysis: {name}", ""]
        price = result.get("price")
        if price is not None:
            lines.append(f"Price: ₹{price:,.2f}")
        pe = result.get("pe")
        div = result.get("dividendYield", 0) or 0
        sector = result.get("sector", "N/A")
        lines.append(f"P/E: {pe if pe is not None else 'N/A'}, Dividend Yield: {div}%, Sector: {sector}")
        interp = result.get("interpretation", "")
        if interp:
            lines.extend(["", "Interpretation:", interp])
        rf = result.get("risk_factors", "")
        if rf:
            lines.extend(["", "Risk Factors:", rf])
        return "\n".join(lines)

    # Comparison (from source)
    if source == "compare_stocks" and result.get("name1"):
        n1, n2 = result.get("name1", ""), result.get("name2", "")
        lines = [f"Comparison: {n1} vs {n2}", "", "Metrics:"]
        p1, p2 = result.get("price1"), result.get("price2")
        pe1, pe2 = result.get("pe1"), result.get("pe2")
        d1 = result.get("dividendYield1") or 0
        d2 = result.get("dividendYield2") or 0
        if p1 is not None:
            lines.append(f"  {n1} – Price: ₹{p1:,.2f}, P/E: {pe1 if pe1 is not None else 'N/A'}, Dividend Yield: {d1}%")
        if p2 is not None:
            lines.append(f"  {n2} – Price: ₹{p2:,.2f}, P/E: {pe2 if pe2 is not None else 'N/A'}, Dividend Yield: {d2}%")
        interp = result.get("interpretation") or []
        if interp:
            lines.extend(["", "Interpretation:"] + [f"  • {x}" for x in interp])
        pref = (result.get("recommendation") or {}).get("preferred")
        if pref:
            lines.extend(["", "Conclusion:", f"  Preferred on metrics: {pref}."])
        return "\n".join(lines)

    # Technical indicators
    if source in {"rsi", "macd", "moving_averages", "technical_analysis"}:
        sym = (result.get("symbol") or "").replace(".NS", "").replace(".BO", "")

        def _fnum(x: Any, *, nd: int = 2) -> str:
            try:
                return f"{float(x):.{nd}f}"
            except Exception:
                return "N/A"

        # RSI
        if source == "rsi":
            if result.get("error"):
                return f"Technical Indicator – {sym}\n\nRSI Value: N/A\n\nInterpretation:\n{result.get('error')}"
            rsi_val = result.get("rsi")
            try:
                rv = float(rsi_val)
            except Exception:
                rv = None
            if rv is None:
                interp = "RSI could not be computed from available price data."
            elif rv > 70:
                interp = "Momentum is very strong and potentially stretched. Overbought can persist in strong trends, but pullback risk increases."
            elif rv < 30:
                interp = "Momentum is weak and potentially stretched. Oversold can indicate a bounce zone, but confirm with trend/support."
            else:
                interp = "Momentum is broadly neutral; look at trend and key price levels for better context."
            return "\n".join(
                [
                    f"Technical Indicator – {sym}",
                    "",
                    f"RSI Value: {_fnum(rv)}",
                    "",
                    "Signal:",
                    "RSI > 70 → Overbought",
                    "RSI < 30 → Oversold",
                    "Else → Neutral",
                    "",
                    "Interpretation:",
                    interp,
                ]
            )

        # MACD
        if source == "macd":
            if result.get("error"):
                return f"Technical Indicator – {sym}\n\nMACD Line: N/A\nSignal Line: N/A\nHistogram: N/A\n\nInterpretation:\n{result.get('error')}"
            macd_v = result.get("macd")
            sig_v = result.get("signal")
            hist_v = result.get("histogram")
            try:
                mv = float(macd_v)
                sv = float(sig_v)
            except Exception:
                mv, sv = None, None
            bullish = (mv is not None and sv is not None and mv > sv)
            bear = (mv is not None and sv is not None and mv < sv)
            signal_txt = "Bullish" if bullish else "Bearish" if bear else "Neutral"
            if bullish:
                interp = "MACD above the signal line suggests bullish momentum is strengthening."
                concl = "Momentum tailwind: trend-following traders often prefer long bias while this holds."
            elif bear:
                interp = "MACD below the signal line suggests bearish momentum is dominating."
                concl = "Momentum headwind: rallies may face selling pressure until MACD crosses back above signal."
            else:
                interp = "MACD is close to the signal line, suggesting indecision in momentum."
                concl = "Wait for a clearer cross (or confirm with trend/levels) before acting."
            return "\n".join(
                [
                    f"Technical Indicator – {sym}",
                    "",
                    f"MACD Line: {_fnum(macd_v)}",
                    f"Signal Line: {_fnum(sig_v)}",
                    f"Histogram: {_fnum(hist_v)}",
                    "",
                    "Signal:",
                    "MACD above signal → Bullish",
                    "MACD below signal → Bearish",
                    "",
                    "Interpretation:",
                    interp,
                    "",
                    "Conclusion:",
                    concl,
                ]
            )

        # Moving averages
        if source == "moving_averages":
            if result.get("error"):
                return f"Technical Indicator – {sym}\n\nCurrent Price: N/A\n\nInterpretation:\n{result.get('error')}"
            price = result.get("price") or result.get("current_price")
            sma20 = result.get("sma20")
            sma50 = result.get("sma50")
            sma200 = result.get("sma200")
            try:
                px = float(price)
            except Exception:
                px = None
            try:
                s20 = float(sma20)
            except Exception:
                s20 = None
            try:
                s50 = float(sma50)
            except Exception:
                s50 = None
            try:
                s200 = float(sma200)
            except Exception:
                s200 = None

            above_200 = (px is not None and s200 is not None and px > s200)
            above_50 = (px is not None and s50 is not None and px > s50)
            above_20 = (px is not None and s20 is not None and px > s20)

            if above_200 and above_50:
                interp = "Price is above key medium/long-term averages, indicating an overall bullish trend structure."
                concl = "Trend bias: bullish."
            elif (px is not None and s200 is not None and px < s200) and (px is not None and s50 is not None and px < s50):
                interp = "Price is below key medium/long-term averages, indicating a bearish trend structure."
                concl = "Trend bias: bearish."
            else:
                interp = "Price is mixed vs moving averages, suggesting a range or transition phase. Use support/resistance for confirmation."
                concl = "Trend bias: neutral/mixed."

            return "\n".join(
                [
                    f"Technical Indicator – {sym}",
                    "",
                    f"Current Price: ₹{_fnum(price)}" if px is not None else "Current Price: N/A",
                    "",
                    "Moving Averages",
                    "",
                    f"20 Day MA: ₹{_fnum(sma20)}",
                    f"50 Day MA: ₹{_fnum(sma50)}",
                    f"200 Day MA: ₹{_fnum(sma200)}",
                    "",
                    "Signal:",
                    "",
                    "Price above MA → Bullish",
                    "Price below MA → Bearish",
                    "",
                    "Interpretation:",
                    interp,
                    "",
                    "Conclusion:",
                    concl,
                ]
            )

        # Combined technical analysis (fallback)
        lines = [f"Technical Analysis – {sym}", ""]
        if result.get("error"):
            return f"Technical Analysis – {sym}: {result.get('error', 'No data')}"
        interp = result.get("interpretation") or []
        if interp:
            lines.extend(interp if isinstance(interp, list) else [interp])
        if result.get("final_signal"):
            lines.append(f"\nFinal signal: {result['final_signal']}")
        return "\n".join(lines)

    # Volume / smart money
    if source == "volume_analysis":
        sym = (result.get("symbol") or "").replace(".NS", "").replace(".BO", "")
        screen = result.get("screen")
        if isinstance(screen, list) and screen:
            lines = ["Volume Analysis – Top unusual volume:", ""]
            for r in screen[:8]:
                s = (r.get("symbol") or "").replace(".NS", "").replace(".BO", "")
                z = r.get("volume_zscore")
                lines.append(f"  • {s}" + (f" (z={z:.1f})" if isinstance(z, (int, float)) else ""))
        else:
            sm = result.get("smart_money") or {}
            lines = [f"Volume Analysis – {sym}", ""]
            if isinstance(sm, dict) and sm:
                z = sm.get("volume_zscore")
                lines.append(f"Volume z-score: {z}" if z is not None else "Volume data available.")
            else:
                lines.append(result.get("note", "No volume data available."))
        return "\n".join(lines)

    # Market news
    if source == "market_news":
        news = result.get("news") or []
        market = result.get("market", "NSE")
        lines = [f"Latest {market} headlines:", ""]
        for n in news[:8]:
            lines.append(f"• {n.get('title', n.get('source', ''))}")
        if not lines[2:]:
            return result.get("interpretation", "No headlines available.")
        return "\n".join(lines)

    # Macro (repo, inflation, gdp)
    if source == "macro":
        return result.get("message", result.get("interpretation", "Macro data available."))

    # Portfolio analysis
    if source == "portfolio_analysis":
        if result.get("error"):
            return str(result.get("error", "Portfolio analysis failed."))
        lines = ["Portfolio Risk Analysis", ""]
        lines.append(f"Diversification Score: {result.get('diversification_score', 'N/A')}/100")
        lines.append(f"Risk Level: {result.get('risk_level', 'N/A')}")
        lines.append("")
        allocs = result.get("allocations") or []
        if allocs:
            lines.append("Allocations:")
            for a in allocs[:10]:
                s = (a.get("symbol") or "").replace(".NS", "").replace(".BO", "")
                w = a.get("weight_percent")
                lines.append(f"  • {s}: {w}%")
        suggestions = result.get("suggestions", "")
        if suggestions:
            lines.extend(["", "Suggestions:", suggestions])
        return "\n".join(lines)

    # Investment advice
    if source == "investment_advice":
        exp = result.get("explanation", "")
        prof = result.get("risk_profile", "moderate")
        lines = [f"Investment Advice (risk profile: {prof})", ""]
        alloc = result.get("sector_allocation") or {}
        if alloc:
            lines.append("Suggested sector allocation:")
            for sec, pct in list(alloc.items())[:8]:
                lines.append(f"  • {sec}: {pct}%")
        if exp:
            lines.extend(["", exp])
        return "\n".join(lines)

    # Market trend (top gainers/losers)
    if source == "market_trend":
        gainers = result.get("gainers") or []
        losers = result.get("losers") or []
        lines = ["Market Momentum", ""]
        if gainers:
            lines.append("Top Gainers:")
            for g in gainers[:5]:
                s = (g.get("symbol") or "").replace(".NS", "").replace(".BO", "")
                ch = g.get("change_percent")
                ch_str = f"{ch:+.2f}%" if isinstance(ch, (int, float)) else "N/A"
                lines.append(f"  • {s}: {ch_str}")
        if losers:
            lines.extend(["", "Top Losers:"])
            for l in losers[:5]:
                s = (l.get("symbol") or "").replace(".NS", "").replace(".BO", "")
                ch = l.get("change_percent")
                ch_str = f"{ch:+.2f}%" if isinstance(ch, (int, float)) else "N/A"
                lines.append(f"  • {s}: {ch_str}")
        return "\n".join(lines) if (gainers or losers) else "No momentum data available."

    # Error fallback
    if result.get("error"):
        return str(result.get("error", "An error occurred."))

    # Generic: try to build minimal readable text
    return result.get("interpretation", result.get("message", "Analysis complete."))


def _build_chat_response_legacy(
    query: str,
    parsed: Dict[str, Any],
    analysis: Dict[str, Any],
    *,
    stock_report: Optional[str] = None,
    portfolio_report: Optional[str] = None,
    market_report: Optional[str] = None,
    insights: Optional[List[str]] = None,
) -> str:
    """Assemble a concise, conversational answer (advisor_v5_routes)."""
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

