"""
Portfolio analysis and segmentation service.
"""

from typing import Any, Dict, List

import yfinance as yf

from app.services.sector_service import SECTOR_STOCKS
from app.utils.rate_limiter import rate_limit
from app.utils.yfinance_wrapper import fetch_history


def _find_sector_for_symbol(symbol: str) -> str:
    symbol = symbol.upper()
    for sector, symbols in SECTOR_STOCKS.items():
        if symbol in symbols:
            return sector
    return "others"


@rate_limit(calls_per_minute=3)
def analyze_portfolio(stocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze a portfolio of stocks.

    Input format:
    [
        {"symbol": "RELIANCE.NS", "quantity": 10, "buy_price": 2000},
        ...
    ]
    """
    if not isinstance(stocks, list) or not stocks:
        return {"error": "stocks must be a non-empty list."}

    max_segment_size = 5
    enriched_stocks: List[Dict[str, Any]] = []

    # Segment portfolio into chunks of 5 to avoid API overload
    for i in range(0, len(stocks), max_segment_size):
        segment = stocks[i : i + max_segment_size]
        symbols = [str(s.get("symbol", "")).upper().strip() for s in segment if s.get("symbol")]
        symbols = [s for s in symbols if s]
        if not symbols:
            continue

        try:
            data = yf.download(symbols, period="2d", group_by="ticker", auto_adjust=False, progress=False)
        except Exception:
            data = None

        for original in segment:
            symbol = str(original.get("symbol", "")).upper().strip()
            quantity = float(original.get("quantity", 0) or 0)
            buy_price = float(original.get("buy_price", 0) or 0)

            if not symbol or quantity <= 0 or buy_price <= 0:
                continue

            current_price = None
            day_change_percent = 0.0

            try:
                if data is not None and not data.empty:
                    if isinstance(data.columns, tuple) or "Close" in data.columns:
                        # Single ticker case
                        hist = data
                        close = hist["Close"]
                    else:
                        # Multi-ticker: group_by=ticker returns dict-like access via data[symbol]
                        hist = data[symbol]
                        close = hist["Close"]

                    if len(close) >= 2:
                        last = float(close.iloc[-1])
                        prev = float(close.iloc[-2])
                        current_price = last
                        if prev:
                            day_change_percent = (last - prev) / prev * 100
                if current_price is None:
                    hist_fallback = fetch_history(symbol, period="2d", ttl=60)
                    if hist_fallback is not None and not hist_fallback.empty and len(hist_fallback) >= 2:
                        last_row = hist_fallback.iloc[-1]
                        prev_row = hist_fallback.iloc[-2]
                        current_price = float(last_row["Close"])
                        prev_close = float(prev_row["Close"])
                        if prev_close:
                            day_change_percent = (current_price - prev_close) / prev_close * 100
            except Exception:
                current_price = None

            if current_price is None:
                continue

            invested_value = buy_price * quantity
            current_value = current_price * quantity
            profit_loss = current_value - invested_value
            profit_loss_percent = (profit_loss / invested_value * 100) if invested_value else 0.0

            sector = _find_sector_for_symbol(symbol)

            enriched_stocks.append(
                {
                    "symbol": symbol,
                    "quantity": quantity,
                    "buy_price": buy_price,
                    "current_price": round(current_price, 2),
                    "current_value": round(current_value, 2),
                    "invested_value": round(invested_value, 2),
                    "profit_loss": round(profit_loss, 2),
                    "profit_loss_percent": round(profit_loss_percent, 2),
                    "day_change_percent": round(day_change_percent, 2),
                    "sector": sector,
                }
            )

    if not enriched_stocks:
        return {"error": "Unable to fetch portfolio data. Please check symbols and try again."}

    total_invested = sum(s["invested_value"] for s in enriched_stocks)
    total_current_value = sum(s["current_value"] for s in enriched_stocks)
    total_profit_loss = total_current_value - total_invested
    total_return_percent = (total_profit_loss / total_invested * 100) if total_invested else 0.0

    best_performer = max(enriched_stocks, key=lambda s: s["profit_loss_percent"])
    worst_performer = min(enriched_stocks, key=lambda s: s["profit_loss_percent"])

    # Sector allocation
    sector_values: Dict[str, float] = {}
    for s in enriched_stocks:
        sector = s["sector"]
        sector_values[sector] = sector_values.get(sector, 0.0) + s["current_value"]

    sector_allocation: Dict[str, float] = {}
    if total_current_value > 0:
        for sector, value in sector_values.items():
            sector_allocation[sector] = round(value / total_current_value * 100, 2)

    # Ideal allocation
    ideal_allocation: Dict[str, float] = {
        "banking": 25,
        "it": 20,
        "pharma": 10,
        "auto": 10,
        "fmcg": 10,
        "energy": 10,
        "metals": 8,
        "others": 7,
    }

    rebalancing_suggestions: Dict[str, str] = {}
    for sector, ideal in ideal_allocation.items():
        actual = sector_allocation.get(sector, 0.0)
        if actual > ideal + 10:
            suggestion = "Overweight - consider reducing"
        elif actual < ideal - 10:
            suggestion = "Underweight - consider adding"
        else:
            suggestion = "Well balanced"
        rebalancing_suggestions[sector] = suggestion

    overall_sentiment = "Profit" if total_profit_loss > 0 else "Loss" if total_profit_loss < 0 else "Flat"

    portfolio_summary = {
        "total_invested": round(total_invested, 2),
        "total_current_value": round(total_current_value, 2),
        "total_profit_loss": round(total_profit_loss, 2),
        "total_return_percent": round(total_return_percent, 2),
        "total_stocks": len(enriched_stocks),
        "best_performer": best_performer,
        "worst_performer": worst_performer,
    }

    return {
        "portfolio_summary": portfolio_summary,
        "stocks": enriched_stocks,
        "sector_allocation": sector_allocation,
        "rebalancing_suggestions": rebalancing_suggestions,
        "overall_sentiment": overall_sentiment,
    }


def get_portfolio_summary(stocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Lightweight version of analyze_portfolio: only returns summary and best/worst performers.
    """
    result = analyze_portfolio(stocks)
    if "error" in result:
        return result

    summary = result.get("portfolio_summary", {})
    return {
        "portfolio_summary": summary,
        "best_performer": summary.get("best_performer"),
        "worst_performer": summary.get("worst_performer"),
    }

