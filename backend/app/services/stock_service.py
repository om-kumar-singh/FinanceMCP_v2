"""
Stock data service using yfinance.
"""

import logging
import math

import pandas_ta as ta

from app.services.market_data_service import safe_fetch_history, safe_fetch_info
from app.services.stock_search_service import resolve_symbol

logger = logging.getLogger(__name__)

# NIFTY 50 symbols (NSE)
NIFTY_50_SYMBOLS = [
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    "INFY.NS",
    "ICICIBANK.NS",
    "HINDUNILVR.NS",
    "ITC.NS",
    "SBIN.NS",
    "BHARTIARTL.NS",
    "KOTAKBANK.NS",
    "LT.NS",
    "AXISBANK.NS",
    "ASIANPAINT.NS",
    "MARUTI.NS",
    "TATAMOTORS.NS",
    "WIPRO.NS",
    "ULTRACEMCO.NS",
    "NESTLEIND.NS",
    "TITAN.NS",
    "BAJFINANCE.NS",
    "BAJAJFINSV.NS",
    "TECHM.NS",
    "HCLTECH.NS",
    "SUNPHARMA.NS",
    "DRREDDY.NS",
    "ONGC.NS",
    "NTPC.NS",
    "POWERGRID.NS",
    "COALINDIA.NS",
    "JSWSTEEL.NS",
]

def _is_nan(v: float) -> bool:
    try:
        fv = float(v)
    except Exception:
        return True
    return fv != fv or math.isnan(fv)


def _error(source: str, message: str, symbol: str | None = None) -> dict:
    payload: dict = {"source": source, "error": message}
    if symbol:
        payload["symbol"] = symbol
    return payload


def get_stock_quote(symbol: str) -> dict | None:
    """
    Fetch stock quote data for the given symbol.

    Args:
        symbol: Stock ticker symbol (e.g., RELIANCE.NS, TCS.NS)

    Returns:
        Dict with quote data, or None if symbol is invalid or no data available.
    """
    if not symbol or not symbol.strip():
        return None

    symbol = symbol.strip().upper()
    if not (symbol.endswith(".NS") or symbol.endswith(".BO")):
        resolved = resolve_symbol(symbol)
        if not resolved:
            return None
        symbol = resolved

    # Fetch 5 days of history to ensure we have previous close
    hist, resolved_symbol, err = safe_fetch_history(symbol, period="5d")
    symbol = resolved_symbol or symbol
    if hist is None:
        return None if err else None

    # Need at least 2 rows for previous close
    if len(hist) < 2:
        return None

    if "Close" not in getattr(hist, "columns", []):
        return _error("market_data", "Market data missing 'Close' column.", symbol)

    latest = hist.iloc[-1]
    previous = hist.iloc[-2]

    try:
        close = float(latest.get("Close"))
        previous_close = float(previous.get("Close"))
    except Exception:
        return _error("market_data", "Invalid close price data received.", symbol)

    price = round(close, 2)
    change = round(close - previous_close, 2)
    change_percent = round((change / previous_close) * 100, 2) if previous_close else 0
    try:
        volume = int(latest.get("Volume")) if "Volume" in latest else 0
    except Exception:
        volume = 0
    try:
        day_high = round(float(latest.get("High")), 2) if "High" in latest else price
    except Exception:
        day_high = price
    try:
        day_low = round(float(latest.get("Low")), 2) if "Low" in latest else price
    except Exception:
        day_low = price

    return {
        "symbol": symbol,
        "price": price,
        "change": change,
        "change_percent": change_percent,
        "volume": volume,
        "day_high": day_high,
        "day_low": day_low,
    }


def get_stock_detail(symbol: str) -> dict | None:
    """
    Fetch stock quote plus fundamentals (PE, dividend yield, market cap, sector) for the AI advisor.

    Returns:
        Dict with symbol, price, pe, dividendYield, marketCap, sector (and quote fields), or None.
    """
    quote = get_stock_quote(symbol)
    if quote is None:
        return None

    symbol_clean = quote["symbol"]
    info, _ = safe_fetch_info(symbol_clean)

    pe = info.get("trailingPE") or info.get("forwardPE")
    if pe is not None:
        try:
            pe = round(float(pe), 1)
        except Exception:
            pe = None

    # Dividend yield (percent)
    # Prefer correct formula: annual_dividend / price * 100 using dividendRate when available.
    # Fallback to yfinance's dividendYield (ratio) when dividendRate is missing.
    div_yield = 0.0
    try:
        price = float(quote.get("price") or 0)
    except Exception:
        price = 0.0
    dividend_rate = info.get("dividendRate")  # annual cash dividend per share (usually)
    dividend_yield_ratio = info.get("dividendYield")  # typically ratio (0.02 => 2%)

    computed = None
    if dividend_rate is not None and price > 0:
        try:
            computed = (float(dividend_rate) / price) * 100.0
        except Exception:
            computed = None

    fallback = None
    if dividend_yield_ratio is not None:
        try:
            fallback = float(dividend_yield_ratio) * 100.0 if dividend_yield_ratio else 0.0
        except Exception:
            fallback = None

    # Choose the more plausible value when both exist.
    if computed is not None and computed >= 0:
        if fallback is not None and fallback >= 0:
            # If one value is clearly unrealistic, choose the other.
            if computed > 30 and fallback <= 30:
                div_yield = fallback
            elif fallback > 30 and computed <= 30:
                div_yield = computed
            else:
                # Otherwise prefer computed formula.
                div_yield = computed
        else:
            div_yield = computed
    elif fallback is not None and fallback >= 0:
        div_yield = fallback

    div_yield = round(float(div_yield), 2)

    mcap = info.get("marketCap")
    try:
        mcap_val = float(mcap) if mcap is not None else None
    except Exception:
        mcap_val = None
    if mcap_val is not None and mcap_val > 0:
        if mcap_val >= 1_00_000_00_00_000:  # >= 1L Cr
            market_cap_str = f"{mcap_val / 1_00_000_00_00_000:.1f}L Cr"
        elif mcap_val >= 1_00_000_00_000:  # >= 1000 Cr
            market_cap_str = f"{mcap_val / 1_00_000_00_000:.0f} Cr"
        else:
            market_cap_str = f"{mcap_val / 1_00_000_00:.0f} Cr"
    else:
        market_cap_str = "N/A"

    sector = (info.get("sector") or "N/A").strip() or "N/A"

    return {
        "symbol": symbol_clean,
        "price": quote["price"],
        "pe": pe,
        "dividendYield": div_yield,
        "marketCap": market_cap_str,
        "sector": sector,
        "change": quote.get("change"),
        "change_percent": quote.get("change_percent"),
        "volume": quote.get("volume"),
        "day_high": quote.get("day_high"),
        "day_low": quote.get("day_low"),
    }


def get_stock_history(symbol: str, period: str = "6mo") -> dict | None:
    """
    Fetch OHLCV history for charts. period: 1mo, 3mo, 6mo, 1y.

    Returns:
        Dict with symbol, period, dates[], opens[], highs[], lows[], closes[], volumes[],
        or None if invalid. All numeric arrays for Recharts.
    """
    if not symbol or not symbol.strip():
        return None

    symbol = symbol.strip().upper()
    if not (symbol.endswith(".NS") or symbol.endswith(".BO")):
        resolved = resolve_symbol(symbol)
        if not resolved:
            return None
        symbol = resolved

    if period not in ("1mo", "3mo", "6mo", "1y", "2y"):
        period = "6mo"

    hist, resolved_symbol, _err = safe_fetch_history(symbol, period=period)
    symbol = resolved_symbol or symbol
    if hist is None or len(hist) < 2:
        return None

    if "Close" not in getattr(hist, "columns", []):
        return None

    hist = hist.reset_index()
    if "Date" not in hist.columns and "Datetime" in hist.columns:
        hist["Date"] = hist["Datetime"]

    dates = []
    opens = []
    highs = []
    lows = []
    closes = []
    volumes = []

    for _, row in hist.iterrows():
        d = row.get("Date")
        if hasattr(d, "strftime"):
            dates.append(d.strftime("%Y-%m-%d"))
        else:
            dates.append(str(d)[:10])
        try:
            opens.append(round(float(row.get("Open", 0) or 0), 2))
        except Exception:
            opens.append(0)
        try:
            highs.append(round(float(row.get("High", 0) or 0), 2))
        except Exception:
            highs.append(0)
        try:
            lows.append(round(float(row.get("Low", 0) or 0), 2))
        except Exception:
            lows.append(0)
        try:
            closes.append(round(float(row.get("Close", 0) or 0), 2))
        except Exception:
            closes.append(0)
        try:
            volumes.append(int(row.get("Volume", 0) or 0))
        except Exception:
            volumes.append(0)

    return {
        "symbol": symbol,
        "period": period,
        "dates": dates,
        "opens": opens,
        "highs": highs,
        "lows": lows,
        "closes": closes,
        "volumes": volumes,
    }


def calculate_rsi(symbol: str, period: int = 14) -> dict | None:
    """
    Calculate RSI (Relative Strength Index) for the given symbol.

    Args:
        symbol: Stock ticker symbol (e.g., RELIANCE.NS, TCS.NS)
        period: RSI lookback period (default 14)

    Returns:
        Dict with RSI data, or None if symbol is invalid or insufficient data.
    """
    if not symbol or not symbol.strip():
        return None

    if period < 2:
        return None

    symbol = symbol.strip().upper()
    if not (symbol.endswith(".NS") or symbol.endswith(".BO")):
        resolved = resolve_symbol(symbol)
        if not resolved:
            return None
        symbol = resolved

    # Fetch enough history for RSI (period * 2 ensures sufficient data)
    days_needed = max(period * 2, 60)
    hist, resolved_symbol, err = safe_fetch_history(symbol, period=f"{days_needed}d")
    symbol = resolved_symbol or symbol
    if hist is None:
        return _error("market_data", err or "No market data available for symbol", symbol)

    if "Close" not in getattr(hist, "columns", []):
        return _error("market_data", "Market data missing 'Close' column.", symbol)

    close = hist["Close"].dropna()
    if len(close) < period + 1:
        return _error("indicator", "Not enough data for indicator calculation", symbol)

    try:
        rsi_series = ta.rsi(close, length=period)
    except Exception:
        logger.error("RSI calculation failed: symbol=%s period=%s", symbol, period, exc_info=True)
        return _error("indicator", "RSI calculation failed", symbol)

    if rsi_series is None or rsi_series.empty:
        return _error("indicator", "RSI calculation returned empty result", symbol)

    try:
        latest_rsi = float(rsi_series.iloc[-1])
    except Exception:
        return _error("indicator", "RSI calculation returned invalid value", symbol)

    if _is_nan(latest_rsi):
        return _error("indicator", "RSI calculation returned NaN (insufficient warmup)", symbol)

    if latest_rsi > 70:
        signal = "overbought"
    elif latest_rsi < 30:
        signal = "oversold"
    else:
        signal = "neutral"

    return {
        "symbol": symbol,
        "rsi": round(latest_rsi, 2),
        "period": period,
        "signal": signal,
    }


def calculate_macd(symbol: str) -> dict | None:
    """
    Calculate MACD (Moving Average Convergence Divergence) for the given symbol.

    Args:
        symbol: Stock ticker symbol (e.g., RELIANCE.NS, TCS.NS)

    Returns:
        Dict with MACD data, or None if symbol is invalid or insufficient data.
    """
    if not symbol or not symbol.strip():
        return None

    symbol = symbol.strip().upper()
    if not (symbol.endswith(".NS") or symbol.endswith(".BO")):
        resolved = resolve_symbol(symbol)
        if not resolved:
            return None
        symbol = resolved

    # Fetch at least 60 days of history for MACD (needs ~35+ for default 12/26/9)
    hist, resolved_symbol, err = safe_fetch_history(symbol, period="60d")
    symbol = resolved_symbol or symbol
    if hist is None:
        return _error("market_data", err or "No market data available for symbol", symbol)

    if "Close" not in getattr(hist, "columns", []):
        return _error("market_data", "Market data missing 'Close' column.", symbol)

    close = hist["Close"].dropna()
    if len(close) < 35:
        return _error("indicator", "Not enough data for indicator calculation", symbol)

    try:
        macd_df = ta.macd(close, fast=12, slow=26, signal=9)
    except Exception:
        logger.error("MACD calculation failed: symbol=%s", symbol, exc_info=True)
        return _error("indicator", "MACD calculation failed", symbol)

    if macd_df is None or macd_df.empty:
        return _error("indicator", "MACD calculation returned empty result", symbol)

    # pandas_ta returns DataFrame with MACD line, Signal line, Histogram columns
    cols = macd_df.columns.tolist()
    if len(cols) < 3:
        return _error("indicator", "MACD calculation returned unexpected output", symbol)

    latest = macd_df.iloc[-1]
    try:
        macd_line = float(latest[cols[0]])
        signal_line = float(latest[cols[1]])
        histogram = float(latest[cols[2]])
    except Exception:
        return _error("indicator", "MACD calculation returned invalid values", symbol)

    # Handle NaN from insufficient warmup
    if any(_is_nan(v) for v in (macd_line, signal_line, histogram)):
        return _error("indicator", "MACD calculation returned NaN (insufficient warmup)", symbol)

    trend = "bullish" if macd_line > signal_line else "bearish"

    return {
        "symbol": symbol,
        "macd": round(macd_line, 2),
        "signal": round(signal_line, 2),
        "histogram": round(histogram, 2),
        "trend": trend,
    }


def get_top_gainers_losers(count: int = 10) -> dict | None:
    """
    Fetch NIFTY 50 stocks and return top N gainers and top N losers by daily % change.

    Args:
        count: Number of top gainers and losers to return (default 10)

    Returns:
        Dict with gainers and losers lists, or None on error.
    """
    if count < 1 or count > 50:
        return None

    results = []
    for symbol in NIFTY_50_SYMBOLS:
        hist, resolved_symbol, _err = safe_fetch_history(symbol, period="5d")
        if hist is None or len(hist) < 2:
            continue
        if "Close" not in getattr(hist, "columns", []):
            continue
        latest = hist.iloc[-1]
        previous = hist.iloc[-2]
        try:
            close = float(latest.get("Close"))
            previous_close = float(previous.get("Close"))
        except Exception:
            continue
        change_percent = round((close - previous_close) / previous_close * 100, 2) if previous_close else 0
        results.append({
            "symbol": resolved_symbol or symbol,
            "price": round(close, 2),
            "change_percent": change_percent,
        })

    if not results:
        return None

    sorted_by_change = sorted(results, key=lambda x: x["change_percent"], reverse=True)
    gainers = sorted_by_change[:count]
    losers = sorted_by_change[-count:][::-1]

    return {
        "gainers": gainers,
        "losers": losers,
    }


def calculate_moving_averages(symbol: str) -> dict | None:
    """
    Calculate SMA20, SMA50, SMA200 and current price vs each MA.

    Args:
        symbol: Stock ticker symbol (e.g., RELIANCE.NS, TCS.NS)

    Returns:
        Dict with price, SMAs, and signal (above/below) for each, or None if invalid.
    """
    if not symbol or not symbol.strip():
        return None

    symbol = symbol.strip().upper()
    if not (symbol.endswith(".NS") or symbol.endswith(".BO")):
        resolved = resolve_symbol(symbol)
        if not resolved:
            return None
        symbol = resolved

    hist, resolved_symbol, err = safe_fetch_history(symbol, period="1y")
    symbol = resolved_symbol or symbol
    if hist is None:
        return _error("market_data", err or "No market data available for symbol", symbol)

    if "Close" not in getattr(hist, "columns", []):
        return _error("market_data", "Market data missing 'Close' column.", symbol)

    close = hist["Close"].dropna()
    if len(close) < 200:
        return _error("indicator", "Not enough data for indicator calculation", symbol)

    try:
        sma20 = ta.sma(close, length=20)
        sma50 = ta.sma(close, length=50)
        sma200 = ta.sma(close, length=200)
    except Exception:
        logger.error("Moving averages calculation failed: symbol=%s", symbol, exc_info=True)
        return _error("indicator", "Moving averages calculation failed", symbol)

    if sma20 is None or sma50 is None or sma200 is None:
        return _error("indicator", "Moving averages calculation returned empty result", symbol)

    try:
        latest_close = float(close.iloc[-1])
        latest_sma20 = float(sma20.iloc[-1])
        latest_sma50 = float(sma50.iloc[-1])
        latest_sma200 = float(sma200.iloc[-1])
    except Exception:
        return _error("indicator", "Moving averages calculation returned invalid values", symbol)

    if any(_is_nan(v) for v in (latest_sma20, latest_sma50, latest_sma200)):
        return _error("indicator", "Moving averages calculation returned NaN (insufficient warmup)", symbol)

    def _signal(price: float, ma: float) -> str:
        return "above" if price > ma else "below"

    return {
        "symbol": symbol,
        "price": round(latest_close, 2),
        "sma20": round(latest_sma20, 2),
        "sma50": round(latest_sma50, 2),
        "sma200": round(latest_sma200, 2),
        "signal_sma20": _signal(latest_close, latest_sma20),
        "signal_sma50": _signal(latest_close, latest_sma50),
        "signal_sma200": _signal(latest_close, latest_sma200),
    }


def calculate_bollinger_bands(symbol: str) -> dict | None:
    """
    Calculate Bollinger Bands (length=20, std=2) for the given symbol.

    Args:
        symbol: Stock ticker symbol (e.g., RELIANCE.NS, TCS.NS)

    Returns:
        Dict with upper, middle, lower bands and signal (overbought/oversold/neutral), or None if invalid.
    """
    if not symbol or not symbol.strip():
        return None

    symbol = symbol.strip().upper()
    if not (symbol.endswith(".NS") or symbol.endswith(".BO")):
        resolved = resolve_symbol(symbol)
        if not resolved:
            return None
        symbol = resolved

    hist, resolved_symbol, err = safe_fetch_history(symbol, period="60d")
    symbol = resolved_symbol or symbol
    if hist is None:
        return _error("market_data", err or "No market data available for symbol", symbol)

    if "Close" not in getattr(hist, "columns", []):
        return _error("market_data", "Market data missing 'Close' column.", symbol)

    close = hist["Close"].dropna()
    if len(close) < 25:
        return _error("indicator", "Not enough data for indicator calculation", symbol)

    try:
        bbands_df = ta.bbands(close, length=20, std=2)
    except Exception:
        logger.error("Bollinger Bands calculation failed: symbol=%s", symbol, exc_info=True)
        return _error("indicator", "Bollinger Bands calculation failed", symbol)

    if bbands_df is None or bbands_df.empty:
        return _error("indicator", "Bollinger Bands calculation returned empty result", symbol)

    cols = bbands_df.columns.tolist()
    if len(cols) < 3:
        return _error("indicator", "Bollinger Bands calculation returned unexpected output", symbol)

    latest = bbands_df.iloc[-1]
    try:
        lower = float(latest[cols[0]])
        middle = float(latest[cols[1]])
        upper = float(latest[cols[2]])
    except Exception:
        return _error("indicator", "Bollinger Bands calculation returned invalid values", symbol)

    if any(_is_nan(v) for v in (lower, middle, upper)):
        return _error("indicator", "Bollinger Bands returned NaN (insufficient warmup)", symbol)

    try:
        price = float(close.iloc[-1])
    except Exception:
        return _error("market_data", "Invalid close price data received.", symbol)

    if price > upper:
        signal = "overbought"
    elif price < lower:
        signal = "oversold"
    else:
        signal = "neutral"

    return {
        "symbol": symbol,
        "price": round(price, 2),
        "upper": round(upper, 2),
        "middle": round(middle, 2),
        "lower": round(lower, 2),
        "signal": signal,
    }
