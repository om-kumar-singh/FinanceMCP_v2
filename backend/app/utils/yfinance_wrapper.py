"""
Centralized yfinance wrapper with caching and timeout.

All yfinance calls in the backend should go through this module.
"""

from __future__ import annotations

import concurrent.futures
from typing import Any, Optional

import yfinance as yf

from app.utils.cache import cache


def fetch_history(
    ticker_symbol: str,
    period: str = "2d",
    interval: Optional[str] = None,
    start: Optional[str] = None,
    ttl: int = 60,
) -> Any:
    """
    Fetch yfinance history with caching and 8s timeout.

    Returns: pandas DataFrame (empty on failure)
    """
    cache_key = f"hist_{ticker_symbol}_{period}_{interval or ''}_{start or ''}"
    cached = cache.get(cache_key)
    if cached is not None:
        print(f"[CACHE HIT] hist_{ticker_symbol}_{period}")
        return cached

    def _do_fetch():
        ticker = yf.Ticker(ticker_symbol)
        if start:
            return ticker.history(start=start)
        if interval:
            return ticker.history(period=period, interval=interval)
        return ticker.history(period=period)

    try:
        with concurrent.futures.ThreadPoolExecutor() as ex:
            future = ex.submit(_do_fetch)
            result = future.result(timeout=8)
        if result is not None and not getattr(result, "empty", True):
            cache.set(cache_key, result, ttl)
        import pandas as pd

        return result if result is not None and not result.empty else pd.DataFrame()
    except Exception as e:
        print(f"[yfinance] history fetch failed for {ticker_symbol}: {e}")
        import pandas as pd

        return pd.DataFrame()


def fetch_info(ticker_symbol: str, ttl: int = 300) -> dict[str, Any]:
    """
    Fetch yfinance Ticker.info with caching and 8s timeout.

    Returns: dict (empty on failure)
    """
    cache_key = f"info_{ticker_symbol}"
    cached = cache.get(cache_key)
    if cached is not None:
        print(f"[CACHE HIT] info_{ticker_symbol}")
        return cached

    def _do_fetch():
        return yf.Ticker(ticker_symbol).info

    try:
        with concurrent.futures.ThreadPoolExecutor() as ex:
            future = ex.submit(_do_fetch)
            result = future.result(timeout=8)
        if result and isinstance(result, dict):
            cache.set(cache_key, result, ttl)
        return result if result and isinstance(result, dict) else {}
    except Exception as e:
        print(f"[yfinance] info fetch failed for {ticker_symbol}: {e}")
        return {}


def fetch_news(ticker_symbol: str, ttl: int = 300) -> list:
    """
    Fetch yfinance Ticker.news with caching and 8s timeout.

    Returns: list of news dicts (empty on failure)
    """
    cache_key = f"news_{ticker_symbol}"
    cached = cache.get(cache_key)
    if cached is not None:
        print(f"[CACHE HIT] news_{ticker_symbol}")
        return cached

    def _do_fetch():
        return getattr(yf.Ticker(ticker_symbol), "news", None) or []

    try:
        with concurrent.futures.ThreadPoolExecutor() as ex:
            future = ex.submit(_do_fetch)
            result = future.result(timeout=8)
        items = result if isinstance(result, list) else []
        if items:
            cache.set(cache_key, items, ttl)
        return items
    except Exception as e:
        print(f"[yfinance] news fetch failed for {ticker_symbol}: {e}")
        return []
