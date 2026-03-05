"""
Advisor V2 API routes.

Adds optional, richer endpoints:
- POST /advisor/v2/stock
- POST /advisor/v2/portfolio

These endpoints do not modify or replace any existing behaviour. They
return data using the familiar {"query", "source", "result"} pattern
so the front‑end Chat component can adopt them later with minimal
changes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field, conlist, confloat

from app.services.advisor_v2.explanation_engine import (
    summarise_portfolio_recommendation,
    summarise_stock_recommendation,
)
from app.services.advisor_v2.portfolio_risk import analyse_portfolio_v2
from app.services.advisor_v2.signal_scoring import score_stock_signal


advisor_v2_router = APIRouter(prefix="/advisor/v2", tags=["advisor_v2"])


Horizon = Literal["intraday", "short", "medium"]


class StockAdvisorV2Request(BaseModel):
    symbol: str = Field(..., description="NSE/BSE symbol, e.g. RELIANCE.NS")
    horizon: Horizon = Field(
        "short",
        description="Time horizon for the ensemble forecast: intraday (1d), short (~5d), medium (~20d).",
    )
    risk_profile: Optional[Literal["conservative", "moderate", "aggressive"]] = Field(
        None,
        description="Optional user risk profile for future use.",
    )


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


class PortfolioAdvisorV2Request(BaseModel):
    stocks: PortfolioStocksList = Field(
        ...,
        description="Portfolio positions; same format as /portfolio/analyze.",
    )
    risk_profile: Optional[Literal["conservative", "moderate", "aggressive"]] = Field(
        None,
        description="Optional risk profile used when shaping portfolio level suggestions.",
    )


@advisor_v2_router.post(
    "/stock",
    summary="Advisor V2 – Stock analysis",
    response_description="Advisor V2 stock analysis in source/result format.",
)
def advisor_v2_stock(payload: StockAdvisorV2Request) -> Dict[str, Any]:
    """
    Enhanced single‑stock analysis endpoint.

    Response format (OpenAPI contract):

    {
      "query": "<symbol and horizon>",
      "source": "advisor_v2_stock",
      "result": {
        "symbol": "RELIANCE.NS",
        "quote": {...},                 # existing get_stock_detail shape
        "ensemble": {...},              # prediction_engine.ensemble_forecast()
        "technical_score": {...},       # indicators + technical score
        "signal": {
          "action": "buy" | "hold" | "reduce" | "avoid" | "strong_buy",
          "score": 0-100
        },
        "risk_metrics": {
          "expected_volatility": float | null
        },
        "confidence": {
          "score": float,               # 0–1
          "label": "low" | "medium" | "high" | "unknown"
        },
        "explanation": {
          "summary": str,
          "drivers": [str, ...],
          "caveats": [str, ...]
        }
      }
    }
    """
    symbol = payload.symbol
    horizon = payload.horizon

    signal_payload = score_stock_signal(symbol, horizon=horizon)
    explanation = summarise_stock_recommendation(signal_payload)

    ensemble = signal_payload.get("ensemble") or {}
    risk_metrics = {
        "expected_volatility": ensemble.get("expected_volatility"),
    }
    confidence = ensemble.get("confidence") or {
        "score": 0.0,
        "label": "unknown",
    }

    return {
        "query": f"{symbol} ({horizon})",
        "source": "advisor_v2_stock",
        "result": {
            "symbol": signal_payload.get("symbol", symbol),
            "quote": signal_payload.get("quote"),
            "ensemble": ensemble,
            "technical_score": signal_payload.get("technical_score"),
            "signal": signal_payload.get("signal"),
            "risk_metrics": risk_metrics,
            "confidence": confidence,
            "explanation": explanation,
        },
    }


@advisor_v2_router.post(
    "/portfolio",
    summary="Advisor V2 – Portfolio risk analysis",
    response_description="Advisor V2 portfolio analysis in source/result format.",
)
def advisor_v2_portfolio(payload: PortfolioAdvisorV2Request) -> Dict[str, Any]:
    """
    Enhanced portfolio‑level analysis endpoint.

    Request body is intentionally aligned with /portfolio/analyze so the
    front‑end can reuse its models:

    {
      "stocks": [
        {"symbol": "RELIANCE.NS", "quantity": 10, "buy_price": 2000},
        ...
      ],
      "risk_profile": "moderate"
    }

    Response (OpenAPI contract):

    {
      "query": "<N stocks, profile>",
      "source": "advisor_v2_portfolio",
      "result": {
        "portfolio": {
          "summary": {...},             # from analyze_portfolio
          "stocks": [...],              # enriched positions
          "sector_allocation": {...},
          "rebalancing_suggestions": {...},
          "overall_sentiment": "Profit" | "Loss" | "Flat"
        },
        "risk_metrics": {
          "volatility": float,
          "sharpe": float,
          "diversification_score": float,
          "max_position_weight_percent": float,
          "sector_weights": { "banking": 25.0, ... }
        },
        "recommendation": {
          "summary": str,
          "drivers": [str, ...],
          "caveats": [str, ...]
        },
        "confidence": {
          "score": float,
          "label": "low" | "medium" | "high"
        }
      }
    }
    """
    stocks_payload: List[Dict[str, Any]] = [
        {"symbol": s.symbol, "quantity": s.quantity, "buy_price": s.buy_price}
        for s in payload.stocks
    ]

    base_and_risk = analyse_portfolio_v2(stocks_payload)
    if base_and_risk.get("error"):
        # Pass through the same error contract style used by existing routes
        return {
            "query": f"{len(stocks_payload)} stocks",
            "source": "advisor_v2_portfolio",
            "result": base_and_risk,
        }

    expl = summarise_portfolio_recommendation(base_and_risk)
    risk_metrics = base_and_risk.get("risk_metrics", {})

    # Confidence: higher for more diversified portfolios with stable metrics
    div_score = float(risk_metrics.get("diversification_score", 0.0))
    vol = float(risk_metrics.get("volatility", 0.0))

    base_conf = 0.5 + (div_score / 300.0)
    if vol > 0.03:
        base_conf -= 0.1
    confidence_score = max(0.1, min(0.95, base_conf))
    if confidence_score >= 0.75:
        label = "high"
    elif confidence_score >= 0.45:
        label = "medium"
    else:
        label = "low"

    portfolio_block = base_and_risk.get("base", {})

    return {
        "query": f"{len(stocks_payload)} stocks, profile={payload.risk_profile or 'unspecified'}",
        "source": "advisor_v2_portfolio",
        "result": {
            "portfolio": {
                "summary": portfolio_block.get("portfolio_summary"),
                "stocks": portfolio_block.get("stocks"),
                "sector_allocation": portfolio_block.get("sector_allocation"),
                "rebalancing_suggestions": portfolio_block.get("rebalancing_suggestions"),
                "overall_sentiment": portfolio_block.get("overall_sentiment"),
            },
            "risk_metrics": risk_metrics,
            "recommendation": expl,
            "confidence": {
                "score": round(confidence_score, 3),
                "label": label,
            },
        },
    }

