"""
Market news API routes.
"""

import logging

from fastapi import APIRouter

from app.services.news_service import get_market_news

logger = logging.getLogger(__name__)

news_router = APIRouter(prefix="/news", tags=["news"])


@news_router.get("/{symbol}")
def market_news(symbol: str):
    """
    Get latest market news for a given symbol.
    Only returns data fetched from live APIs; no mock headlines.
    """
    try:
        items = get_market_news(symbol)
        if not items:
            # No live data available; return an empty payload instead of mock data.
            return {"news": [], "summary": "News temporarily unavailable.", "error": "no_live_news"}

        # Preserve link and timestamp information so the frontend can navigate
        # to the actual article URLs while still providing a stable "source"
        # field for display.
        news_list = []
        for x in items:
            title = x.get("title")
            publisher = x.get("publisher") or x.get("source") or "Market"
            link = x.get("link") or x.get("url")
            published_at = x.get("publishedAt") or x.get("published_at")
            url_to_image = x.get("urlToImage") or x.get("image") or ""

            news_list.append(
                {
                    "title": title,
                    "publisher": publisher,
                    "source": publisher,
                    "link": link,
                    "url": link,
                    "publishedAt": published_at,
                    "urlToImage": url_to_image,
                }
            )

        first = (news_list[0].get("title") or "")[:80]
        summary = f"NSE Market Update: {first}." if first else "Latest market headlines."
        return {"news": news_list, "summary": summary}
    except Exception:
        logger.error("News API failed: symbol=%s", symbol, exc_info=True)
        # On failure, do not fall back to mock data; just return an empty payload.
        return {
            "news": [],
            "summary": "News temporarily unavailable.",
            "error": "news_api_failed",
        }

