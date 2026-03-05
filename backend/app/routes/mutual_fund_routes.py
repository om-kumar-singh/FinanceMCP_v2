"""
Mutual fund and SIP API routes.
"""

import logging

from fastapi import APIRouter, HTTPException

from app.services.mutual_fund_service import (
    calculate_capital_gains,
    calculate_sip,
    get_mutual_fund_nav,
    search_mutual_funds,
)

logger = logging.getLogger(__name__)

mutual_fund_router = APIRouter(tags=["mutual-fund"])


@mutual_fund_router.get("/mutual-fund/{scheme_code}")
def mutual_fund_nav(scheme_code: str):
    """
    Get latest NAV for a mutual fund scheme.

    Example: GET /mutual-fund/119551
    """
    try:
        data = get_mutual_fund_nav(scheme_code)
    except Exception:
        logger.error("Mutual fund NAV API failed: scheme_code=%s", scheme_code, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Mutual fund service temporarily unavailable. Please try again.",
        )
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"No NAV data for scheme code '{scheme_code}'. Check if the scheme code is valid.",
        )
    return data


@mutual_fund_router.get("/sip")
def sip_calculator(
    monthly_investment: float,
    years: int,
    annual_return: float,
):
    """
    Calculate SIP future value.

    Example: GET /sip?monthly_investment=5000&years=10&annual_return=12
    """
    if monthly_investment < 0:
        raise HTTPException(
            status_code=400,
            detail="monthly_investment must be non-negative.",
        )
    if years < 1 or years > 50:
        raise HTTPException(
            status_code=400,
            detail="years must be between 1 and 50.",
        )
    if annual_return < 0 or annual_return > 100:
        raise HTTPException(
            status_code=400,
            detail="annual_return must be between 0 and 100.",
        )
    return calculate_sip(monthly_investment, years, annual_return)


@mutual_fund_router.get("/mutual-fund/search")
def mutual_fund_search(query: str):
    """
    Search mutual funds by name or keyword.

    Example: GET /mutual-fund/search?query=hdfc tax saver
    """
    if not query or not query.strip():
        raise HTTPException(
            status_code=400,
            detail="query must be a non-empty string.",
        )

    try:
        data = search_mutual_funds(query)
    except Exception:
        logger.error("Mutual fund search API failed: query=%s", query, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Unable to search mutual funds. Service temporarily unavailable.",
        )
    if data is None:
        raise HTTPException(
            status_code=503,
            detail="Unable to search mutual funds. Service temporarily unavailable.",
        )

    if not data:
        return {
            "query": query,
            "results": [],
            "message": f"No mutual funds found for query '{query}'.",
        }

    return {
        "query": query,
        "results": data,
    }


@mutual_fund_router.get("/capital-gains")
def capital_gains(
    buy_price: float,
    sell_price: float,
    quantity: int,
    holding_days: int,
    asset_type: str = "equity",
):
    """
    Calculate capital gains and tax for equity or debt investments.

    Example:
    GET /capital-gains?buy_price=2000&sell_price=2800&quantity=10&holding_days=400&asset_type=equity
    """
    if buy_price <= 0:
        raise HTTPException(
            status_code=400,
            detail="buy_price must be greater than 0.",
        )
    if sell_price <= 0:
        raise HTTPException(
            status_code=400,
            detail="sell_price must be greater than 0.",
        )
    if quantity < 1:
        raise HTTPException(
            status_code=400,
            detail="quantity must be at least 1.",
        )
    if holding_days < 1:
        raise HTTPException(
            status_code=400,
            detail="holding_days must be at least 1.",
        )

    atype = (asset_type or "").strip().lower()
    if atype not in ("equity", "debt"):
        raise HTTPException(
            status_code=400,
            detail="asset_type must be 'equity' or 'debt'.",
        )

    return calculate_capital_gains(
        buy_price=buy_price,
        sell_price=sell_price,
        quantity=quantity,
        holding_days=holding_days,
        asset_type=atype,
    )
