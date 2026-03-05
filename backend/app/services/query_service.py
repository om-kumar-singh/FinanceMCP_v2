"""
Rule-based query processing for financial questions.
Tool-based AI advisor: intents for stock_price, pe_ratio, dividend_yield,
compare_stocks, buy_recommendation, market_news, stock_analysis.
"""

import re
from typing import Any

from app.services.ipo_service import get_upcoming_ipos
from app.services.macro_service import get_gdp, get_inflation, get_repo_rate
from app.services.mutual_fund_service import calculate_sip, get_mutual_fund_nav

# Stock name to symbol mapping (NSE) – used by intent parser and tools
STOCK_SYMBOLS = {
    "reliance": "RELIANCE.NS",
    "reli": "RELIANCE.NS",
    "tcs": "TCS.NS",
    "infosys": "INFY.NS",
    "infy": "INFY.NS",
    "hdfc": "HDFCBANK.NS",
    "hdfc bank": "HDFCBANK.NS",
    "hdfcbank": "HDFCBANK.NS",
    "sbi": "SBIN.NS",
    "icici": "ICICIBANK.NS",
    "icici bank": "ICICIBANK.NS",
    "bharti": "BHARTIARTL.NS",
    "airtel": "BHARTIARTL.NS",
    "itc": "ITC.NS",
    "wipro": "WIPRO.NS",
    "axis": "AXISBANK.NS",
    "axis bank": "AXISBANK.NS",
    "kotak": "KOTAKBANK.NS",
    "kotak bank": "KOTAKBANK.NS",
    "lt": "LT.NS",
    "larsen": "LT.NS",
    "asian paint": "ASIANPAINT.NS",
    "asianpaint": "ASIANPAINT.NS",
    "maruti": "MARUTI.NS",
    "tata": "TATAMOTORS.NS",
    "tata motors": "TATAMOTORS.NS",
}
DEFAULT_STOCK = "RELIANCE.NS"
DEFAULT_SCHEME_CODE = "119551"

# Rough sector average PE for buy-recommendation interpretation (approximate)
SECTOR_AVG_PE = {
    "Energy": 14,
    "Technology": 25,
    "Financial Services": 14,
    "Consumer Defensive": 22,
    "Communication Services": 18,
    "Industrials": 20,
    "Healthcare": 28,
    "Basic Materials": 12,
    "N/A": 18,
}


def _extract_stock_symbol(query: str) -> str:
    """Extract stock symbol from query using keyword matching."""
    q = query.lower()
    for name, symbol in sorted(STOCK_SYMBOLS.items(), key=lambda x: -len(x[0])):
        if name in q:
            return symbol
    # Check for symbol pattern like RELIANCE.NS or TCS.NS
    match = re.search(r"\b([A-Z]{2,10}\.NS)\b", query, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return DEFAULT_STOCK


def _extract_scheme_code(query: str) -> str:
    """Extract mutual fund scheme code from query."""
    match = re.search(r"\b(\d{5,6})\b", query)
    return match.group(1) if match else DEFAULT_SCHEME_CODE


def _extract_sip_params(query: str) -> tuple[float, int, float]:
    """Extract SIP params: monthly_investment, years, annual_return."""
    numbers = re.findall(r"\b(\d+(?:\.\d+)?)\b", query)
    nums = [float(n) for n in numbers]
    monthly = 5000.0
    years = 10
    annual = 12.0
    if len(nums) >= 1:
        monthly = nums[0]
    if len(nums) >= 2:
        years = int(nums[1])
    if len(nums) >= 3:
        annual = nums[2]
    # Check for percentage
    pct_match = re.search(r"(\d+(?:\.\d+)?)\s*%", query)
    if pct_match:
        annual = float(pct_match.group(1))
    return (monthly, years, annual)


def _extract_two_stocks(query: str) -> tuple[str, str] | None:
    """Extract two stock symbols for compare intent: 'compare X and Y', 'X vs Y'."""
    q = query.lower()
    # "compare X and Y" / "compare X vs Y"
    for sep in (" and ", " vs ", " versus "):
        if "compare" in q and sep in q:
            parts = re.split(re.escape(sep), q, maxsplit=1)
            if len(parts) == 2:
                left = parts[0].replace("compare", "").strip()
                right = parts[1].strip()
                s1 = _symbol_from_token(left)
                s2 = _symbol_from_token(right)
                if s1 and s2 and s1 != s2:
                    return (s1, s2)
    # "X and Y" / "X vs Y" without "compare"
    for sep in (" and ", " vs ", " versus "):
        if sep in q:
            parts = q.split(sep, 1)
            if len(parts) == 2:
                s1 = _symbol_from_token(parts[0].strip())
                s2 = _symbol_from_token(parts[1].strip())
                if s1 and s2 and s1 != s2:
                    return (s1, s2)
    return None


def _symbol_from_token(token: str) -> str | None:
    """Map a single token (e.g. 'hdfc', 'reliance') to NSE symbol."""
    if not token or len(token) > 20:
        return None
    t = token.lower().strip()
    for name, symbol in sorted(STOCK_SYMBOLS.items(), key=lambda x: -len(x[0])):
        if name in t or t in name:
            return symbol
    if re.match(r"^[a-z0-9]{2,10}$", t):
        return f"{t.upper()}.NS"
    return None


def _extract_portfolio_symbols(query: str) -> list[str]:
    """Extract list of stock symbols from 'my portfolio has SBI, TCS, ITC' or 'SBI TCS ITC'."""
    q = query.lower()
    # Remove leading phrase
    for prefix in ("my portfolio has", "portfolio has", "portfolio contains", "portfolio:", "i have", "i hold"):
        if prefix in q:
            q = q.split(prefix, 1)[-1].strip()
    # Split by comma or "and"
    parts = re.split(r"[,،\s]+|(?:\s+and\s+)", q)
    seen = set()
    symbols = []
    for p in parts:
        p = p.strip().strip(".")
        if not p or len(p) < 2:
            continue
        s = _symbol_from_token(p)
        if s and s not in seen:
            seen.add(s)
            symbols.append(s)
    return symbols


def process_query(query: str) -> dict[str, Any]:
    """
    Process natural language financial query using rule-based intent detection.
    Supports: compare_stocks, buy_recommendation, market_news, stock_analysis,
    pe_ratio, dividend_yield, stock_price, plus SIP/RSI/MACD/MF/IPO/macro etc.
    """
    if not query or not str(query).strip():
        return {"message": "I can help with stock prices, valuation analysis, technical indicators, market news, and stock comparisons."}

    q = str(query).strip().lower()

    # ---------- AI Advisor intents (tool-based) ----------

    # MARKET TREND (gainers/losers, nifty trend)
    if any(x in q for x in ("market trend", "nifty trend", "market today", "top gainer", "top loser", "gainers", "losers")):
        from app.services.stock_service import get_top_gainers_losers

        result = get_top_gainers_losers(count=5)
        if result:
            return {"query": query, "result": result, "source": "market_trend"}

    # PORTFOLIO ANALYSIS: "my portfolio has SBI, TCS, ITC"
    if "portfolio" in q and ("has" in q or "contains" in q or "hold" in q or "," in q):
        symbols = _extract_portfolio_symbols(query)
        if len(symbols) >= 1:
            from app.services.stock_service import get_stock_detail

            details = []
            sectors = {}
            for sym in symbols[:10]:
                d = get_stock_detail(sym)
                if d:
                    details.append(d)
                    sec = d.get("sector") or "N/A"
                    sectors[sec] = sectors.get(sec, 0) + 1
            if details:
                diversification = "Concentrated in few sectors." if len(sectors) <= 2 else "Reasonable sector diversification."
                risk_note = "Consider adding defensive or different sectors." if len(sectors) <= 1 else "Diversification helps reduce sector risk."
                return {
                    "query": query,
                    "result": {
                        "stocks": [{"symbol": x["symbol"], "price": x["price"], "sector": x.get("sector"), "pe": x.get("pe")} for x in details],
                        "sector_breakdown": sectors,
                        "diversification": diversification,
                        "risk_note": risk_note,
                        "suggestions": risk_note,
                    },
                    "source": "portfolio_analysis",
                }

    # TECHNICAL ANALYSIS (combined RSI + MACD + MA with interpretation)
    if ("technical" in q and ("analysis" in q or "analyze" in q)) or ("rsi" in q and "macd" in q):
        from app.services.stock_service import calculate_rsi, calculate_macd, calculate_moving_averages

        symbol = _extract_stock_symbol(query)
        rsi = calculate_rsi(symbol)
        macd = calculate_macd(symbol)
        ma = calculate_moving_averages(symbol)
        if rsi or macd or ma:
            name = (rsi or macd or ma)["symbol"].replace(".NS", "").replace(".BO", "")
            interp = []
            if rsi:
                sig = rsi.get("signal", "")
                if sig == "overbought":
                    interp.append(f"RSI {rsi.get('rsi')} suggests overbought—caution on fresh longs.")
                elif sig == "oversold":
                    interp.append(f"RSI {rsi.get('rsi')} suggests oversold—potential bounce.")
                else:
                    interp.append(f"RSI {rsi.get('rsi')} in neutral zone.")
            if ma:
                if ma.get("signal_sma200") == "above":
                    interp.append(f"Price above 200-day MA (₹{ma.get('sma200')}) indicating bullish trend.")
                else:
                    interp.append(f"Price below 200-day MA (₹{ma.get('sma200')}); watch for support.")
            if macd:
                interp.append(f"MACD {macd.get('trend', '')} momentum.")
            return {
                "query": query,
                "result": {
                    "title": f"Technical Analysis: {name}",
                    "symbol": symbol,
                    "rsi": rsi,
                    "macd": macd,
                    "moving_averages": ma,
                    "interpretation": interp,
                },
                "source": "technical_analysis",
            }

    # COMPARE STOCKS
    if ("compare" in q) or (" vs " in q) or (" versus " in q):
        two = _extract_two_stocks(query)
        if two:
            from app.services.stock_service import get_stock_detail

            s1, s2 = two
            d1, d2 = get_stock_detail(s1), get_stock_detail(s2)
            if d1 and d2:
                name1 = d1["symbol"].replace(".NS", "").replace(".BO", "")
                name2 = d2["symbol"].replace(".NS", "").replace(".BO", "")
                interp = []
                if d1.get("pe") is not None and d2.get("pe") is not None:
                    if d1["pe"] < d2["pe"]:
                        interp.append(f"Lower PE of {name1} may indicate relatively cheaper valuation.")
                    elif d2["pe"] < d1["pe"]:
                        interp.append(f"Lower PE of {name2} may indicate relatively cheaper valuation.")
                return {
                    "query": query,
                    "result": {
                        "name1": name1,
                        "name2": name2,
                        "price1": d1["price"],
                        "price2": d2["price"],
                        "pe1": d1.get("pe"),
                        "pe2": d2.get("pe"),
                        "dividendYield1": d1.get("dividendYield", 0),
                        "dividendYield2": d2.get("dividendYield", 0),
                        "interpretation": interp,
                    },
                    "source": "compare_stocks",
                }

    # BUY RECOMMENDATION (includes "undervalued")
    if any(
        x in q
        for x in (
            "good buy",
            "buy now",
            "should i buy",
            "worth buying",
            "good time to buy",
            "is it good to buy",
            "undervalued",
            "overvalued",
        )
    ):
        from app.services.stock_service import get_stock_detail

        symbol = _extract_stock_symbol(query)
        detail = get_stock_detail(symbol)
        if detail:
            sector = detail.get("sector") or "N/A"
            sector_pe = SECTOR_AVG_PE.get(sector, SECTOR_AVG_PE["N/A"])
            pe = detail.get("pe")
            interp = ""
            if pe is not None:
                if pe < sector_pe:
                    interp = f"{detail['symbol'].replace('.NS', '')} is trading below sector average PE ({sector} avg ~{sector_pe}), which may indicate undervaluation."
                else:
                    interp = f"Trading at PE {pe} vs sector average ~{sector_pe}; consider fundamentals and growth."
            risk = "PSU banking exposure; interest rate sensitivity." if "SBIN" in symbol or "bank" in q else "Sector and macro risks; do your own research."
            return {
                "query": query,
                "result": {
                    "symbol": detail["symbol"],
                    "price": detail["price"],
                    "pe": pe,
                    "sector": sector,
                    "sector_avg_pe": sector_pe,
                    "interpretation": interp,
                    "risk_factors": risk,
                    "conclusion": "Evaluate long-term fundamentals before investing.",
                },
                "source": "buy_recommendation",
            }

    # MARKET NEWS
    if any(x in q for x in ("news", "nse news", "market news", "show nse", "show news", "headlines")):
        from app.services.news_service import get_market_news
        from app.services.mock_data import sample_mock_news

        market = "NSE"
        if "bse" in q or "sensex" in q:
            market = "BSE"
        items = get_market_news(market)
        if not items:
            mock = sample_mock_news(market=market, k=5)
            return {
                "query": query,
                "result": {"news": mock["news"], "market": market, "summary": mock["summary"]},
                "source": "market_news",
            }
        return {
            "query": query,
            "result": {"news": items, "market": market},
            "source": "market_news",
        }

    # STOCK ANALYSIS (analyze / analysis + stock name)
    if ("analyze" in q or "analysis" in q) and any(
        w in q for w in ("stock", "reliance", "tcs", "sbi", "hdfc", "icici", "infosys", "itc", "wipro", "axis")
    ):
        from app.services.stock_service import get_stock_detail

        symbol = _extract_stock_symbol(query)
        detail = get_stock_detail(symbol)
        if detail:
            sector = detail.get("sector") or "N/A"
            sector_pe = SECTOR_AVG_PE.get(sector, SECTOR_AVG_PE["N/A"])
            pe = detail.get("pe")
            interp = ""
            if pe is not None:
                if pe < sector_pe:
                    interp = f"{detail['symbol'].replace('.NS', '')} appears undervalued vs sector average PE (~{sector_pe})."
                else:
                    interp = f"Trading slightly above sector average PE (~{sector_pe}); moderate valuation."
            name = detail["symbol"].replace(".NS", "").replace(".BO", "")
            risk = "Sector and macro risks; interest rate sensitivity for banks." if "BANK" in symbol or "SBIN" in symbol else "Sector and market risks; do your own research."
            if "RELIANCE" in symbol:
                risk = "Energy and retail exposure; regulatory and global oil price risks."
            return {
                "query": query,
                "result": {
                    "title": f"Stock Analysis: {name}",
                    "symbol": detail["symbol"],
                    "price": detail["price"],
                    "pe": pe,
                    "dividendYield": detail.get("dividendYield", 0),
                    "marketCap": detail.get("marketCap"),
                    "sector": sector,
                    "sector_avg_pe": sector_pe,
                    "interpretation": interp,
                    "risk_factors": risk,
                },
                "source": "stock_analysis",
            }

    # PE RATIO
    if "pe ratio" in q or " p/e " in q or "pe of" in q or "what is pe" in q or "trailing pe" in q:
        from app.services.stock_service import get_stock_detail

        symbol = _extract_stock_symbol(query)
        detail = get_stock_detail(symbol)
        if detail and detail.get("pe") is not None:
            return {
                "query": query,
                "result": {"symbol": detail["symbol"], "pe": detail["pe"], "price": detail["price"]},
                "source": "pe_ratio",
            }

    # DIVIDEND YIELD
    if "dividend" in q and ("yield" in q or "percent" in q or "stock" in q or any(n in q for n in STOCK_SYMBOLS)):
        from app.services.stock_service import get_stock_detail

        symbol = _extract_stock_symbol(query)
        detail = get_stock_detail(symbol)
        if detail:
            return {
                "query": query,
                "result": {
                    "symbol": detail["symbol"],
                    "dividendYield": detail.get("dividendYield", 0),
                    "price": detail["price"],
                },
                "source": "dividend_yield",
            }

    # STOCK PRICE (single stock – use detail for advisor format)
    if any(w in q for w in ("price", "stock price", "how much", "what is the price", "current price", "quote")):
        from app.services.stock_service import get_stock_detail

        symbol = _extract_stock_symbol(query)
        detail = get_stock_detail(symbol)
        if detail:
            return {
                "query": query,
                "result": {
                    "symbol": detail["symbol"],
                    "price": detail["price"],
                    "pe": detail.get("pe"),
                    "dividendYield": detail.get("dividendYield", 0),
                    "marketCap": detail.get("marketCap"),
                    "sector": detail.get("sector"),
                    "change": detail.get("change"),
                    "change_percent": detail.get("change_percent"),
                },
                "source": "stock_api",
            }

    # ---------- Existing rules (SIP, RSI, MACD, etc.) ----------

    # SIP: "sip" keyword
    if "sip" in q:
        monthly, years, annual = _extract_sip_params(query)
        result = calculate_sip(monthly, years, annual)
        return {"query": query, "result": result, "source": "sip"}

    # RSI: "rsi" keyword
    if "rsi" in q:
        from app.services.stock_service import calculate_rsi

        symbol = _extract_stock_symbol(query)
        result = calculate_rsi(symbol)
        if result is None:
            return {"query": query, "result": {"error": f"No RSI data for {symbol}"}, "source": "rsi"}
        return {"query": query, "result": result, "source": "rsi"}

    # MACD: "macd" keyword
    if "macd" in q:
        from app.services.stock_service import calculate_macd

        symbol = _extract_stock_symbol(query)
        result = calculate_macd(symbol)
        if result is None:
            return {"query": query, "result": {"error": f"No MACD data for {symbol}"}, "source": "macd"}
        return {"query": query, "result": result, "source": "macd"}

    # GAINERS/LOSERS: "gainer" or "loser" keyword
    if "gainer" in q or "loser" in q:
        from app.services.stock_service import get_top_gainers_losers

        result = get_top_gainers_losers(count=10)
        if result is None:
            return {"query": query, "result": {"error": "Unable to fetch gainers/losers data"}, "source": "gainers_losers"}
        return {"query": query, "result": result, "source": "gainers_losers"}

    # MOVING AVERAGES: "moving average" or "sma" or "ma" keyword (exclude macd, macro)
    if "moving average" in q or "sma" in q or ("ma" in q and "macd" not in q and "macro" not in q):
        from app.services.stock_service import calculate_moving_averages

        symbol = _extract_stock_symbol(query)
        result = calculate_moving_averages(symbol)
        if result is None:
            return {"query": query, "result": {"error": f"No moving averages data for {symbol}"}, "source": "moving_averages"}
        return {"query": query, "result": result, "source": "moving_averages"}

    # BOLLINGER BANDS: "bollinger" or "bb" keyword
    if "bollinger" in q or "bb" in q:
        from app.services.stock_service import calculate_bollinger_bands

        symbol = _extract_stock_symbol(query)
        result = calculate_bollinger_bands(symbol)
        if result is None:
            return {"query": query, "result": {"error": f"No Bollinger Bands data for {symbol}"}, "source": "bollinger"}
        return {"query": query, "result": result, "source": "bollinger"}

    # MUTUAL FUND SEARCH: "search"/"find" + "fund" or "mutual fund" + name
    if (
        ("search" in q and "fund" in q)
        or ("find" in q and "fund" in q)
        or ("mutual fund" in q and not re.search(r"\b(\d{5,6})\b", q))
    ):
        from app.services.mutual_fund_service import search_mutual_funds

        search_query = "large cap"

        # Prefer term after "search" or "find"
        for keyword in ("search", "find"):
            idx = q.find(keyword)
            if idx != -1:
                raw = query[idx + len(keyword) :].strip(" :,-")
                if raw:
                    search_query = raw
                    break

        # If still default and "mutual fund" present, take text after it
        if search_query == "large cap" and "mutual fund" in q:
            idx = q.find("mutual fund")
            raw = query[idx + len("mutual fund") :].strip(" :,-")
            if raw:
                search_query = raw

        result = search_mutual_funds(search_query)
        if result is None:
            return {
                "query": query,
                "result": {"error": "Unable to search mutual funds"},
                "source": "mutual_fund_search",
            }
        if not result:
            return {
                "query": query,
                "result": {"funds": [], "message": f"No mutual funds found for '{search_query}'."},
                "source": "mutual_fund_search",
            }
        return {
            "query": query,
            "result": {"funds": result, "query": search_query},
            "source": "mutual_fund_search",
        }

    # MUTUAL FUND: "mutual fund" or "nav"
    if "mutual fund" in q or ("nav" in q and "mutual" not in q):
        scheme_code = _extract_scheme_code(query)
        result = get_mutual_fund_nav(scheme_code)
        if result is None:
            return {"query": query, "result": {"error": f"No NAV data for scheme {scheme_code}"}, "source": "mutual_fund"}
        return {"query": query, "result": result, "source": "mutual_fund"}

    # IPO GMP: "gmp" or "grey market" keyword
    if "gmp" in q or "grey market" in q:
        from app.services.ipo_service import get_gmp

        ipo_name = None

        # Prefer text after "gmp of"
        lower_q = q
        if "gmp of" in lower_q:
            idx = lower_q.find("gmp of")
            raw = query[idx + len("gmp of") :].strip(" :,-?.")
            ipo_name = raw or None
        elif "grey market" in lower_q:
            idx = lower_q.find("grey market")
            raw = query[idx + len("grey market") :].strip(" :,-?.")
            ipo_name = raw or None

        result = get_gmp(ipo_name)
        if result is None:
            return {
                "query": query,
                "result": {"error": "Unable to fetch GMP data"},
                "source": "gmp",
            }
        return {"query": query, "result": result, "source": "gmp"}

    # IPO PERFORMANCE: "ipo performance", "listing gain", or "ipo return"
    if "ipo performance" in q or "listing gain" in q or "ipo return" in q:
        from app.services.ipo_service import get_ipo_performance

        numbers = re.findall(r"\b(\d+)\b", query)
        limit = int(numbers[0]) if numbers else 10
        if limit < 1:
            limit = 10

        result = get_ipo_performance(limit=limit)
        if result is None:
            return {
                "query": query,
                "result": {"error": "Unable to fetch IPO performance data"},
                "source": "ipo_performance",
            }
        return {"query": query, "result": result, "source": "ipo_performance"}

    # SME STOCK ANALYSIS: "sme" + "stock" or "sme" + "analysis"
    if "sme" in q and ("stock" in q or "analysis" in q):
        from app.services.ipo_service import get_sme_stock_analysis

        symbol_match = re.search(r"\b([A-Z]{1,10}\.(?:NS|BO))\b", query, re.IGNORECASE)
        if symbol_match:
            symbol = symbol_match.group(1).upper()
        else:
            symbol = "DELHIVERY.NS"

        result = get_sme_stock_analysis(symbol)
        if result is None:
            return {
                "query": query,
                "result": {"error": f"No SME stock data for {symbol}"},
                "source": "sme_stock",
            }
        return {"query": query, "result": result, "source": "sme_stock"}

    # SECTOR PERFORMANCE: "sector" + sector name
    if "sector" in q:
        from app.services.sector_service import get_all_sectors_summary, get_sector_performance, SECTOR_STOCKS

        # Specific sector query
        for sector_key in SECTOR_STOCKS.keys():
            if sector_key in q:
                result = get_sector_performance(sector_key)
                return {"query": query, "result": result, "source": "sector_performance"}

        # All sectors / summary style query
        if (
            "all sector" in q
            or "sector summary" in q
            or "best sector" in q
            or "which sector" in q
        ):
            result = get_all_sectors_summary()
            return {"query": query, "result": result, "source": "sector_summary"}

    # IPO: "ipo" keyword (including "upcoming ipo")
    if "ipo" in q:
        result = get_upcoming_ipos()
        if result is None:
            return {"query": query, "result": {"error": "Unable to fetch IPO data"}, "source": "ipo"}
        return {"query": query, "result": result, "source": "ipo"}

    # PORTFOLIO: guidance to use the portfolio API
    if "portfolio" in q and ("analyze" in q or "rebalance" in q or "my portfolio" in q):
        message = (
            "To analyze your portfolio, please use POST /portfolio/analyze with your stock list. "
            "Format: [{'symbol': 'RELIANCE.NS', 'quantity': 10, 'buy_price': 2000}]."
        )
        return {"query": query, "message": message, "source": "portfolio_hint"}

    # CAPITAL GAINS / TAX: "capital gain" or tax-related keywords
    if (
        "capital gain" in q
        or "stcg" in q
        or "ltcg" in q
        or ("tax" in q and ("stock" in q or "invest" in q or "investment" in q))
    ):
        from app.services.mutual_fund_service import calculate_capital_gains

        numbers = re.findall(r"\b(\d+(?:\.\d+)?)\b", query)
        buy_price = float(numbers[0]) if len(numbers) >= 1 else 0.0
        sell_price = float(numbers[1]) if len(numbers) >= 2 else 0.0
        quantity = int(float(numbers[2])) if len(numbers) >= 3 else 1
        holding_days = int(float(numbers[3])) if len(numbers) >= 4 else 365

        asset_type = "equity"
        if "debt" in q:
            asset_type = "debt"

        result = calculate_capital_gains(
            buy_price=buy_price,
            sell_price=sell_price,
            quantity=quantity,
            holding_days=holding_days,
            asset_type=asset_type,
        )
        return {"query": query, "result": result, "source": "capital_gains"}

    # MACRO: repo, inflation, gdp
    if "repo" in q:
        result = get_repo_rate()
        return {"query": query, "result": result, "source": "macro"}
    if "inflation" in q:
        result = get_inflation()
        if result is None:
            return {"query": query, "result": {"error": "Unable to fetch inflation data"}, "source": "macro"}
        return {"query": query, "result": result, "source": "macro"}
    if "gdp" in q:
        result = get_gdp()
        if result is None:
            return {"query": query, "result": {"error": "Unable to fetch GDP data"}, "source": "macro"}
        return {"query": query, "result": result, "source": "macro"}

    # STOCK: price, stock, share
    if any(w in q for w in ("price", "stock", "share", "quote")):
        from app.services.stock_service import get_stock_quote

        symbol = _extract_stock_symbol(query)
        result = get_stock_quote(symbol)
        if result is None:
            return {"query": query, "result": {"error": f"No data for {symbol}"}, "source": "stock_api"}
        return {"query": query, "result": result, "source": "stock_api"}

    return {"message": "I can help with stock prices, valuation analysis, technical indicators, market news, and stock comparisons."}
