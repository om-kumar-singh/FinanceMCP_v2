"""
Macroeconomic data API routes.
"""

from fastapi import APIRouter, HTTPException

from app.services.macro_service import get_gdp, get_inflation, get_repo_rate

macro_router = APIRouter(tags=["macro"])


@macro_router.get("/repo-rate")
def repo_rate():
    """
    Get latest RBI repo rate.

    Example: GET /repo-rate
    """
    return get_repo_rate()


@macro_router.get("/inflation")
def inflation():
    """
    Get India CPI inflation for last 3 years.

    Example: GET /inflation
    """
    data = get_inflation()
    if data is None:
        raise HTTPException(
            status_code=503,
            detail="Unable to fetch inflation data. Service temporarily unavailable.",
        )
    return data


@macro_router.get("/gdp")
def gdp():
    """
    Get India GDP growth for last 3 years.

    Example: GET /gdp
    """
    data = get_gdp()
    if data is None:
        raise HTTPException(
            status_code=503,
            detail="Unable to fetch GDP data. Service temporarily unavailable.",
        )
    return data
