"""
Shared market data fetch utilities (yfinance) with guardrails.

Goal: never raise to API route handlers; always return (data, error).
"""

from __future__ import annotations

import logging
from typing import Any

import yfinance as yf

from app.services.stock_search_service import resolve_symbol

logger = logging.getLogger(__name__)


def normalize_symbol(symbol: str | None) -> str | None:
    """
    Normalize a user-provided symbol to a yfinance-compatible ticker.

    - Accepts already-qualified .NS/.BO tickers
    - Resolves bare NSE symbols / company queries via `resolve_symbol`
    - Passes through index tickers like ^NSEI, ^BSESN
    """
    if symbol is None:
        return None
    s = str(symbol).strip().upper()
    if not s:
        return None

    if s.startswith("^"):
        return s

    if s.endswith(".NS") or s.endswith(".BO"):
        return s

    # Resolve using our existing NSE database service
    resolved = resolve_symbol(s)
    return resolved


def safe_fetch_history(
    symbol: str | None,
    *,
    period: str,
    interval: str | None = None,
) -> tuple[Any | None, str | None, str | None]:
    """
    Safely fetch historical OHLCV data using yfinance.

    Returns:
        (hist_df, resolved_symbol, error_message)
    """
    resolved = normalize_symbol(symbol)
    if not resolved:
        return None, None, "Invalid or unknown symbol"

    try:
        ticker = yf.Ticker(resolved)
        hist = (
            ticker.history(period=period, interval=interval)
            if interval
            else ticker.history(period=period)
        )
    except Exception as e:
        logger.error(
            "yfinance history fetch failed: symbol=%s period=%s interval=%s",
            resolved,
            period,
            interval,
            exc_info=True,
        )
        return None, resolved, str(e)

    if hist is None or getattr(hist, "empty", True):
        return None, resolved, "No data returned from yfinance"

    return hist, resolved, None


def safe_fetch_info(symbol: str | None) -> tuple[dict[str, Any], str | None]:
    """
    Safely fetch yfinance `Ticker.info` dict.

    Returns:
        (info_dict, resolved_symbol)
    """
    resolved = normalize_symbol(symbol)
    if not resolved:
        return {}, None

    try:
        info = yf.Ticker(resolved).info or {}
        if not isinstance(info, dict):
            return {}, resolved
        return info, resolved
    except Exception:
        logger.error("yfinance info fetch failed: symbol=%s", resolved, exc_info=True)
        return {}, resolved

