"""
Advisor V4 API routes.

Adds a quant-analysis endpoint:
- POST /advisor/v4/quant-analysis

This is fully additive and does not modify any existing endpoints.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field, conlist, confloat

from app.services.advisor_v4.quant_engine import quant_analyse


advisor_v4_router = APIRouter(prefix="/advisor/v4", tags=["advisor_v4"])


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


class AdvisorV4Request(BaseModel):
    symbol: str = Field(..., description="Primary stock symbol to analyse.")
    portfolio: Optional[PortfolioStocksList] = Field(
        None,
        description="Optional portfolio context; same schema as /portfolio/analyze.",
    )


@advisor_v4_router.post(
    "/quant-analysis",
    summary="Advisor V4 – Quantitative analysis",
    response_description="Institutional-grade quant analysis combining strategies, risk, regime, and smart money.",
)
def advisor_v4_quant_analysis(payload: AdvisorV4Request) -> Dict[str, Any]:
    """
    High-level Advisor V4 quant endpoint.

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
      "source": "advisor_v4_quant",
      "result": {
        "symbol": "RELIANCE",
        "market_regime": "bull_market",
        "trend_strength": 0.78,
        "volatility_level": "medium",
        "strategy_signal": "BUY",
        "strategy_strength": 0.72,
        "strategy_scores": { ... },
        "institutional_activity": "accumulation",
        "institutional_activity_score": 0.67,
        "risk_level": "medium",
        "risk_summary": { ... },
        "portfolio_impact": "improves diversification",
        "advisor_v3_snapshot": { ... },    // pass-through of V3 advisor analysis
        "explanation": "Momentum and trend-following strategies are aligned...",
        "analytics": {
          "market_regime": { ... },
          "portfolio_risk_metrics": { ... },
          "strategy_scores": { ... },
          "institutional_activity": { ... },
          "factor_analysis": { ... }
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

    q = quant_analyse(payload.symbol, portfolio=portfolio_dicts)

    v3 = q["advisor_v3"]
    strat = q["strategy"]
    smart = q["smart_money"]
    risk = q["risk"]
    portfolio_block = q.get("portfolio")

    # Risk level label for top-level view
    risk_cat = risk.get("risk_category") or "medium"

    explanation_parts = []
    explanation_parts.append(
        f"Market regime is {q.get('market_regime')} with trend strength {q.get('trend_strength')}. "
    )
    explanation_parts.append(
        f"Strategy ensemble points to {strat.get('strategy_signal')} with strength {strat.get('strategy_strength')}. "
    )
    explanation_parts.append(
        f"Smart money activity suggests {smart.get('institutional_activity')} (confidence {smart.get('confidence')}). "
    )
    if portfolio_block:
        explanation_parts.append(
            f"Optimized portfolio shows diversification score {portfolio_block['optimizer'].get('diversification_score')} and risk category {risk_cat}. "
        )
    explanation = "".join(explanation_parts).strip()

    display_symbol = str(q.get("symbol") or payload.symbol).replace(".NS", "").replace(".BO", "")

    analytics = {
        "market_regime": {
            "market_regime": q.get("market_regime"),
            "trend_strength": q.get("trend_strength"),
            "volatility_level": q.get("volatility_level"),
        },
        "portfolio_risk_metrics": risk.get("risk_metrics"),
        "strategy_scores": strat.get("strategy_scores"),
        "institutional_activity": smart,
        "factor_analysis": v3.get("factor_scores"),
    }

    return {
        "query": payload.symbol,
        "source": "advisor_v4_quant",
        "result": {
            "symbol": display_symbol,
            "market_regime": q.get("market_regime"),
            "trend_strength": q.get("trend_strength"),
            "volatility_level": q.get("volatility_level"),
            "strategy_signal": strat.get("strategy_signal"),
            "strategy_strength": strat.get("strategy_strength"),
            "strategy_scores": strat.get("strategy_scores"),
            "institutional_activity": smart.get("institutional_activity"),
            "institutional_activity_score": smart.get("confidence"),
            "confidence": q.get("combined_confidence"),
            "risk_level": risk_cat,
            "risk_summary": risk,
            "portfolio_impact": q.get("portfolio_impact"),
            "advisor_v3_snapshot": v3,
            "explanation": explanation,
            "analytics": analytics,
        },
    }

