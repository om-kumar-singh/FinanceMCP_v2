"""
Advisor V3 API routes.

Adds an optional ChatGPT-style analysis endpoint:

- POST /advisor/v3/analyze

This builds on Advisor V2 without changing any existing endpoints.
Responses follow the familiar {"query", "source", "result"} pattern so
the front-end can adopt V3 gradually.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field, conlist, confloat

from app.services.advisor_v3.reasoning_engine import analyse_symbol_v3


advisor_v3_router = APIRouter(prefix="/advisor/v3", tags=["advisor_v3"])


class PortfolioStock(BaseModel):
    symbol: str = Field(..., description="NSE/BSE symbol, e.g. RELIANCE.NS")
    quantity: confloat(gt=0) = Field(..., description="Number of shares/units held.")
    buy_price: confloat(gt=0) = Field(..., description="Average buy price per share/unit.")


def _portfolio_stocks_list_type():
    """
    Pydantic v1/v2 compatibility:
    - v1: conlist(..., min_items=..., max_items=...)
    - v2: conlist(..., min_length=..., max_length=...)
    """
    try:
        return conlist(PortfolioStock, min_length=1, max_length=50)  # type: ignore[call-arg]
    except TypeError:
        return conlist(PortfolioStock, min_items=1, max_items=50)  # type: ignore[call-arg]


PortfolioStocksList = _portfolio_stocks_list_type()


class AdvisorV3Request(BaseModel):
    symbol: str = Field(..., description="Primary stock symbol to analyse.")
    portfolio: Optional[PortfolioStocksList] = Field(
        None,
        description="Optional portfolio context; same schema as /portfolio/analyze.",
    )


@advisor_v3_router.post(
    "/analyze",
    summary="Advisor V3 – ChatGPT-style stock analysis",
    response_description="ChatGPT-style financial analysis with structured factor scores and reasoning.",
)
def advisor_v3_analyze(payload: AdvisorV3Request) -> Dict[str, Any]:
    """
    High-level AI Financial Advisor V3 endpoint.

    Request:
    {
      "symbol": "RELIANCE.NS",
      "portfolio": [
        {"symbol": "RELIANCE.NS", "quantity": 10, "buy_price": 2000},
        ...
      ]
    }

    Response (OpenAPI contract):

    {
      "query": "RELIANCE.NS",
      "source": "advisor_v3",
      "result": {
        "symbol": "RELIANCE",
        "recommendation": "BUY",
        "confidence": 0.74,
        "expected_return": 0.043,
        "market_regime": "bullish",
        "factor_scores": {
          "prediction": 0.78,
          "momentum": 0.66,
          "sentiment": 0.71,
          "trend": 0.73,
          "volume": 0.62,
          "volatility": 0.55
        },
        "risk_level": "Medium",
        "explanation": "Multiple indicators suggest bullish momentum...",
        "institutional": {
          "model_prediction_breakdown": {...},
          "risk_metrics": {...},       // when portfolio context is supplied
          "signal_strength": 0.74,
          "technical_indicators": {...},
          "sentiment_analysis": {...},
          "market_context": {...}
        }
      }
    }
    """
    portfolio_dicts: Optional[List[Dict[str, Any]]] = None
    if payload.portfolio:
        portfolio_dicts = [
            {"symbol": p.symbol, "quantity": p.quantity, "buy_price": p.buy_price}
            for p in payload.portfolio
        ]

    analysis = analyse_symbol_v3(payload.symbol, portfolio=portfolio_dicts)

    # Ensure symbol in result is cleaned for display while keeping NSE suffix in query.
    display_symbol = str(analysis.get("symbol") or payload.symbol).replace(".NS", "").replace(".BO", "")

    return {
        "query": payload.symbol,
        "source": "advisor_v3",
        "result": {
            "symbol": display_symbol,
            "recommendation": analysis.get("recommendation"),
            "confidence": analysis.get("confidence"),
            "expected_return": analysis.get("expected_return"),
            "market_regime": analysis.get("market_regime"),
            "factor_scores": analysis.get("factor_scores"),
            "risk_level": analysis.get("risk_level"),
            "explanation": analysis.get("explanation"),
            "institutional": analysis.get("institutional"),
        },
    }

