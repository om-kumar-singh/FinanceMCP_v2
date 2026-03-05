"""
Stock API routes.
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from app.services.stock_search_service import (
    get_popular_stocks,
    resolve_symbol,
    search_stocks,
)
from app.services.stock_service import (
    calculate_bollinger_bands,
    calculate_macd,
    calculate_moving_averages,
    calculate_rsi,
    get_stock_detail,
    get_stock_quote,
    get_top_gainers_losers,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stock", tags=["stock"])


@router.get("/search")
def stock_search(q: str = Query("", alias="q"), limit: int = 10):
    """
    Smart search across NSE stocks for autocomplete and symbol lookup.

    Example: GET /stock/search?q=reliance&limit=8
    """
    query = (q or "").strip()
    if not query:
        raise HTTPException(
            status_code=400,
            detail="Query parameter 'q' must be a non-empty string.",
        )
    if limit < 1:
        limit = 1
    results = search_stocks(query, limit=limit)
    return results


@router.get("/popular")
def stock_popular():
    """
    Get list of popular/trending stocks for default suggestions.

    Example: GET /stock/popular
    """
    return get_popular_stocks()


@router.get("/resolve")
def stock_resolve(q: str = Query("", alias="q")):
    """
    Resolve a free-text query to a yfinance symbol.

    Example: GET /stock/resolve?q=reliance
    """
    query = (q or "").strip()
    if not query:
        raise HTTPException(
            status_code=400,
            detail="Query parameter 'q' must be a non-empty string.",
        )
    symbol = resolve_symbol(query)
    return {
        "query": query,
        "symbol": symbol,
        "found": bool(symbol),
    }


@router.get("/{symbol}")
def stock_quote(symbol: str):
    """
    Get stock quote and fundamentals for the given symbol (advisor format).

    Example: GET /stock/RELIANCE, GET /stock/TCS.NS
    Returns: symbol, price, pe, dividendYield, marketCap, sector, plus change/volume etc.
    """
    try:
        data = get_stock_detail(symbol)
    except Exception:
        logger.error("Stock detail failed: symbol=%s", symbol, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Market data service temporarily unavailable. Please try again.",
        )
    if data is None or (isinstance(data, dict) and data.get("error")):
        raise HTTPException(
            status_code=404,
            detail=data.get("error") if isinstance(data, dict) and data.get("error") else f"No data found for symbol '{symbol}'. Check if the symbol is valid.",
        )
    return data


rsi_router = APIRouter(prefix="/rsi", tags=["rsi"])


@rsi_router.get("/{symbol}")
def stock_rsi(symbol: str, period: int = 14):
    """
    Get RSI (Relative Strength Index) for the given symbol.

    Example: GET /rsi/RELIANCE.NS, GET /rsi/TCS.NS?period=14
    """
    if period < 2 or period > 100:
        raise HTTPException(
            status_code=400,
            detail="Period must be between 2 and 100.",
        )
    try:
        data = calculate_rsi(symbol, period=period)
    except Exception:
        logger.error("RSI API failed: symbol=%s period=%s", symbol, period, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="RSI service temporarily unavailable. Please try again.",
        )
    if data is None or (isinstance(data, dict) and data.get("error")):
        raise HTTPException(
            status_code=404,
            detail=data.get("error") if isinstance(data, dict) and data.get("error") else f"No RSI data for symbol '{symbol}'. Check symbol or try a smaller period.",
        )
    return data


macd_router = APIRouter(prefix="/macd", tags=["macd"])


@macd_router.get("/{symbol}")
def stock_macd(symbol: str):
    """
    Get MACD (Moving Average Convergence Divergence) for the given symbol.

    Example: GET /macd/RELIANCE.NS
    """
    try:
        data = calculate_macd(symbol)
    except Exception:
        logger.error("MACD API failed: symbol=%s", symbol, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="MACD service temporarily unavailable. Please try again.",
        )
    if data is None or (isinstance(data, dict) and data.get("error")):
        raise HTTPException(
            status_code=404,
            detail=data.get("error") if isinstance(data, dict) and data.get("error") else f"No MACD data for symbol '{symbol}'. Check if the symbol is valid.",
        )
    return data


gainers_losers_router = APIRouter(prefix="/gainers-losers", tags=["gainers-losers"])


@gainers_losers_router.get("")
def top_gainers_losers(count: int = 10):
    """
    Get top N gainers and losers from NIFTY 50 by daily % change.

    Example: GET /gainers-losers?count=10
    """
    if count < 1 or count > 50:
        raise HTTPException(
            status_code=400,
            detail="Count must be between 1 and 50.",
        )
    try:
        data = get_top_gainers_losers(count=count)
    except Exception:
        logger.error("Gainers/losers API failed: count=%s", count, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Unable to fetch gainers/losers data. Service temporarily unavailable.",
        )
    if data is None:
        raise HTTPException(
            status_code=503,
            detail="Unable to fetch gainers/losers data. Service temporarily unavailable.",
        )
    return data


moving_averages_router = APIRouter(prefix="/moving-averages", tags=["moving-averages"])


@moving_averages_router.get("/{symbol}")
def stock_moving_averages(symbol: str):
    """
    Get SMA20, SMA50, SMA200 and price vs each for the given symbol.

    Example: GET /moving-averages/RELIANCE.NS
    """
    try:
        data = calculate_moving_averages(symbol)
    except Exception:
        logger.error("Moving averages API failed: symbol=%s", symbol, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Moving averages service temporarily unavailable. Please try again.",
        )
    if data is None or (isinstance(data, dict) and data.get("error")):
        raise HTTPException(
            status_code=404,
            detail=data.get("error") if isinstance(data, dict) and data.get("error") else f"No moving averages data for symbol '{symbol}'. Check if the symbol is valid.",
        )
    return data


bollinger_router = APIRouter(prefix="/bollinger", tags=["bollinger"])


@bollinger_router.get("/{symbol}")
def stock_bollinger(symbol: str):
    """
    Get Bollinger Bands for the given symbol.

    Example: GET /bollinger/RELIANCE.NS
    """
    try:
        data = calculate_bollinger_bands(symbol)
    except Exception:
        logger.error("Bollinger API failed: symbol=%s", symbol, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Bollinger Bands service temporarily unavailable. Please try again.",
        )
    if data is None or (isinstance(data, dict) and data.get("error")):
        raise HTTPException(
            status_code=404,
            detail=data.get("error") if isinstance(data, dict) and data.get("error") else f"No Bollinger Bands data for symbol '{symbol}'. Check if the symbol is valid.",
        )
    return data

