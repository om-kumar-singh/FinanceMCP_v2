"""
Mutual fund and SIP API routes.
"""

from fastapi import APIRouter, HTTPException

from app.services.mutual_fund_service import calculate_sip, get_mutual_fund_nav

mutual_fund_router = APIRouter(tags=["mutual-fund"])


@mutual_fund_router.get("/mutual-fund/{scheme_code}")
def mutual_fund_nav(scheme_code: str):
    """
    Get latest NAV for a mutual fund scheme.

    Example: GET /mutual-fund/119551
    """
    data = get_mutual_fund_nav(scheme_code)
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
