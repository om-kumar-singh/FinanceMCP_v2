"""
Sector performance service using yfinance.
"""

from typing import Any

from app.utils.cache import cacheable
from app.utils.rate_limiter import rate_limit
from app.utils.yfinance_wrapper import fetch_history


SECTOR_STOCKS: dict[str, list[str]] = {
    "banking": [
        "HDFCBANK.NS",
        "ICICIBANK.NS",
        "SBIN.NS",
        "KOTAKBANK.NS",
        "AXISBANK.NS",
        "INDUSINDBK.NS",
        "BANDHANBNK.NS",
        "FEDERALBNK.NS",
    ],
    "it": [
        "TCS.NS",
        "INFY.NS",
        "WIPRO.NS",
        "HCLTECH.NS",
        "TECHM.NS",
        "LTIM.NS",
        "MPHASIS.NS",
        "PERSISTENT.NS",
    ],
    "pharma": [
        "SUNPHARMA.NS",
        "DRREDDY.NS",
        "CIPLA.NS",
        "DIVISLAB.NS",
        "BIOCON.NS",
        "AUROPHARMA.NS",
        "LUPIN.NS",
        "TORNTPHARM.NS",
    ],
    "auto": [
        "MARUTI.NS",
        "TATAMOTORS.NS",
        "M&M.NS",
        "BAJAJ-AUTO.NS",
        "HEROMOTOCO.NS",
        "EICHERMOT.NS",
        "ASHOKLEY.NS",
        "TVSMOTOR.NS",
    ],
    "fmcg": [
        "HINDUNILVR.NS",
        "ITC.NS",
        "NESTLEIND.NS",
        "BRITANNIA.NS",
        "DABUR.NS",
        "MARICO.NS",
        "COLPAL.NS",
        "GODREJCP.NS",
    ],
    "energy": [
        "RELIANCE.NS",
        "ONGC.NS",
        "NTPC.NS",
        "POWERGRID.NS",
        "COALINDIA.NS",
        "BPCL.NS",
        "IOC.NS",
        "GAIL.NS",
    ],
    "metals": [
        "TATASTEEL.NS",
        "JSWSTEEL.NS",
        "HINDALCO.NS",
        "VEDL.NS",
        "SAIL.NS",
        "NMDC.NS",
        "JINDALSTEL.NS",
        "NATIONALUM.NS",
    ],
    "realestate": [
        "DLF.NS",
        "GODREJPROP.NS",
        "OBEROIRLTY.NS",
        "PRESTIGE.NS",
        "BRIGADE.NS",
        "SOBHA.NS",
        "PHOENIXLTD.NS",
        "MAHLIFE.NS",
    ],
}


@cacheable(ttl_seconds=300)
@rate_limit(calls_per_minute=3)
def get_sector_performance(sector_name: str) -> dict[str, Any]:
    """
    Get performance metrics for a given sector.
    """
    if not sector_name:
        return {
            "error": "Sector name is required.",
            "available_sectors": sorted(SECTOR_STOCKS.keys()),
        }

    key = sector_name.strip().lower()
    if key not in SECTOR_STOCKS:
        return {
            "error": f"Unknown sector '{sector_name}'.",
            "available_sectors": sorted(SECTOR_STOCKS.keys()),
        }

    symbols = SECTOR_STOCKS[key]
    stocks: list[dict[str, Any]] = []

    for symbol in symbols:
        try:
            hist = fetch_history(symbol, period="5d", ttl=60)
        except Exception:
            continue

        if hist is None or hist.empty:
            continue

        if len(hist) < 2:
            continue

        latest = hist.iloc[-1]
        prev = hist.iloc[-2]
        first = hist.iloc[0]

        try:
            close_today = float(latest["Close"])
            close_prev = float(prev["Close"])
            close_first = float(first["Close"])
        except Exception:
            continue

        if close_prev:
            day_change_percent = (close_today - close_prev) / close_prev * 100
        else:
            day_change_percent = 0.0

        if close_first:
            week_change_percent = (close_today - close_first) / close_first * 100
        else:
            week_change_percent = 0.0

        volume = float(latest["Volume"]) if "Volume" in latest else 0.0

        stocks.append(
            {
                "symbol": symbol,
                "current_price": round(close_today, 2),
                "day_change_percent": round(day_change_percent, 2),
                "week_change_percent": round(week_change_percent, 2),
                "volume": volume,
            }
        )

    if not stocks:
        return {
            "error": f"Unable to fetch data for sector '{sector_name}'.",
            "available_sectors": sorted(SECTOR_STOCKS.keys()),
        }

    day_changes = [s["day_change_percent"] for s in stocks]
    week_changes = [s["week_change_percent"] for s in stocks]

    sector_avg_day_change = sum(day_changes) / len(day_changes)
    sector_avg_week_change = sum(week_changes) / len(week_changes)

    top_performer = max(stocks, key=lambda s: s["day_change_percent"])
    bottom_performer = min(stocks, key=lambda s: s["day_change_percent"])

    advancing = sum(1 for s in stocks if s["day_change_percent"] > 0)
    declining = sum(1 for s in stocks if s["day_change_percent"] < 0)

    if advancing > declining:
        sentiment = "Bullish"
    elif declining > advancing:
        sentiment = "Bearish"
    else:
        sentiment = "Neutral"

    return {
        "sector_name": key,
        "stocks": stocks,
        "sector_avg_day_change": round(sector_avg_day_change, 2),
        "sector_avg_week_change": round(sector_avg_week_change, 2),
        "top_performer": top_performer,
        "bottom_performer": bottom_performer,
        "advancing": advancing,
        "declining": declining,
        "sentiment": sentiment,
    }


@cacheable(ttl_seconds=600)
def get_all_sectors_summary() -> list[dict[str, Any]]:
    """
    Get summary performance across all sectors.
    """
    summaries: list[dict[str, Any]] = []

    for sector in sorted(SECTOR_STOCKS.keys()):
        data = get_sector_performance(sector)
        if not isinstance(data, dict):
            continue
        if data.get("error"):
            continue

        summaries.append(
            {
                "sector_name": data.get("sector_name", sector),
                "sentiment": data.get("sentiment"),
                "avg_day_change": data.get("sector_avg_day_change"),
                "top_performer": data.get("top_performer"),
                "advancing": data.get("advancing"),
                "declining": data.get("declining"),
            }
        )

    summaries.sort(
        key=lambda s: s.get("avg_day_change") if s.get("avg_day_change") is not None else float("-inf"),
        reverse=True,
    )

    return summaries

