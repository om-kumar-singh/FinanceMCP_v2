"""
IPO tracking API routes.
"""

from fastapi import APIRouter

from app.services.ipo_service import get_upcoming_ipos

ipo_router = APIRouter(tags=["ipo"])


@ipo_router.get("/ipos")
def upcoming_ipos():
    """
    Get list of upcoming IPOs (top 5).

    Example: GET /ipos
    """
    data = get_upcoming_ipos()
    if data is None:
        return {"error": "Unable to fetch IPO data"}
    return data
