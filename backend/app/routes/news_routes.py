"""
Market news API routes.
"""

from fastapi import APIRouter

from app.services.news_service import get_market_news
from app.services.mock_data import sample_mock_news


news_router = APIRouter(prefix="/news", tags=["news"])


@news_router.get("/{symbol}")
def market_news(symbol: str):
    """
    Get latest market news for a given symbol.
    Returns mock headlines when external API returns no items (avoids 404).
    Includes a short summary for the UI (headline teaser).
    """
    items = get_market_news(symbol)
    if not items:
        # Varied mock so repeated calls aren't identical
        market = "BSE" if str(symbol).strip().upper() in {"BSE", "SENSEX"} else "NSE"
        return sample_mock_news(market=market, k=5)
    news_list = [{"title": x.get("title"), "source": x.get("publisher") or x.get("source", "Market")} for x in items]
    first = (news_list[0].get("title") or "")[:80]
    summary = f"NSE Market Update: {first}." if first else "Latest market headlines."
    return {"news": news_list, "summary": summary}

