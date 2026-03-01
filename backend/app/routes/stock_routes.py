"""
Stock API routes.
"""

from fastapi import APIRouter, HTTPException

from app.services.stock_service import calculate_macd, calculate_rsi, get_stock_quote

router = APIRouter(prefix="/stock", tags=["stock"])


@router.get("/{symbol}")
def stock_quote(symbol: str):
    """
    Get stock quote for the given symbol.

    Example: GET /stock/RELIANCE.NS, GET /stock/TCS.NS
    """
    data = get_stock_quote(symbol)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for symbol '{symbol}'. Check if the symbol is valid.",
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
    data = calculate_rsi(symbol, period=period)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"No RSI data for symbol '{symbol}'. Check symbol or try a smaller period.",
        )
    return data


macd_router = APIRouter(prefix="/macd", tags=["macd"])


@macd_router.get("/{symbol}")
def stock_macd(symbol: str):
    """
    Get MACD (Moving Average Convergence Divergence) for the given symbol.

    Example: GET /macd/RELIANCE.NS
    """
    data = calculate_macd(symbol)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"No MACD data for symbol '{symbol}'. Check if the symbol is valid.",
        )
    return data
