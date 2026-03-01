"""
Stock data service using yfinance.
"""

import pandas_ta as ta
import yfinance as yf


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
    ticker = yf.Ticker(symbol)

    # Fetch 5 days of history to ensure we have previous close
    hist = ticker.history(period="5d")

    if hist is None or hist.empty:
        return None

    # Need at least 2 rows for previous close
    if len(hist) < 2:
        return None

    latest = hist.iloc[-1]
    previous = hist.iloc[-2]

    close = float(latest["Close"])
    previous_close = float(previous["Close"])
    price = round(close, 2)
    change = round(close - previous_close, 2)
    change_percent = round((change / previous_close) * 100, 2) if previous_close else 0
    volume = int(latest["Volume"]) if "Volume" in latest else 0
    day_high = round(float(latest["High"]), 2) if "High" in latest else price
    day_low = round(float(latest["Low"]), 2) if "Low" in latest else price

    return {
        "symbol": symbol,
        "price": price,
        "change": change,
        "change_percent": change_percent,
        "volume": volume,
        "day_high": day_high,
        "day_low": day_low,
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
    ticker = yf.Ticker(symbol)

    # Fetch enough history for RSI (period * 2 ensures sufficient data)
    days_needed = max(period * 2, 60)
    hist = ticker.history(period=f"{days_needed}d")

    if hist is None or hist.empty:
        return None

    if len(hist) < period + 1:
        return None

    rsi_series = ta.rsi(hist["Close"], length=period)

    if rsi_series is None or rsi_series.empty:
        return None

    latest_rsi = float(rsi_series.iloc[-1])

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
    ticker = yf.Ticker(symbol)

    # Fetch at least 60 days of history for MACD (needs ~35+ for default 12/26/9)
    hist = ticker.history(period="60d")

    if hist is None or hist.empty:
        return None

    if len(hist) < 35:
        return None

    macd_df = ta.macd(hist["Close"], fast=12, slow=26, signal=9)

    if macd_df is None or macd_df.empty:
        return None

    # pandas_ta returns DataFrame with MACD line, Signal line, Histogram columns
    cols = macd_df.columns.tolist()
    if len(cols) < 3:
        return None

    latest = macd_df.iloc[-1]
    macd_line = float(latest[cols[0]])
    signal_line = float(latest[cols[1]])
    histogram = float(latest[cols[2]])

    # Handle NaN from insufficient warmup
    if any(v != v for v in (macd_line, signal_line, histogram)):
        return None

    trend = "bullish" if macd_line > signal_line else "bearish"

    return {
        "symbol": symbol,
        "macd": round(macd_line, 2),
        "signal": round(signal_line, 2),
        "histogram": round(histogram, 2),
        "trend": trend,
    }
