"""
Advisor V5 conversational API routes.

Adds:
- POST /advisor/chat
- GET  /advisor/insights  (optional AI insight feed)

These endpoints are additive and do not modify existing behaviour.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field, conlist, confloat

from app.services.advisor_v4.quant_engine import quant_analyse
from app.services.advisor_v5.financial_reasoner import reason_about_query
from app.services.advisor_v5.insight_engine import generate_insights
from app.services.advisor_v5.query_parser import parse_query
from app.services.advisor_v5.report_generator import (
    build_market_outlook_report,
    build_portfolio_report,
    build_stock_report,
)
from app.services.advisor_v5.response_generator import build_chat_response


advisor_v5_router = APIRouter(prefix="/advisor", tags=["advisor_v5"])


class PortfolioStock(BaseModel):
    symbol: str = Field(..., description="NSE/BSE symbol, e.g. RELIANCE.NS")
    quantity: confloat(gt=0) = Field(..., description="Number of shares/units held.")
    buy_price: confloat(gt=0) = Field(..., description="Average buy price per share/unit.")


class AdvisorChatRequest(BaseModel):
    query: str = Field(..., description="Natural language financial question.")
    portfolio: Optional[conlist(PortfolioStock, min_items=1, max_items=50)] = Field(
        None,
        description="Optional portfolio context for risk/optimization questions.",
    )
    context: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional conversational context from the caller (e.g. last_symbol).",
    )


@advisor_v5_router.post(
    "/chat",
    summary="Advisor V5 – Conversational financial assistant",
    response_description="ChatGPT-style natural language response using Advisor V1–V4 analytics.",
)
def advisor_v5_chat(payload: AdvisorChatRequest) -> Dict[str, Any]:
    """
    Conversational endpoint for financial Q&A.

    Input:
    {
      "query": "Should I buy Reliance right now?",
      "portfolio": [...],     // optional
      "context": {...}        // optional
    }

    Output:
    {
      "source": "advisor_v5",
      "response": "<natural language answer>",
      "analytics": {
        "intent": "...",
        "parsed": {...},
        "analysis": {...},
        "insights": [...]
      }
    }
    """
    portfolio_dicts: Optional[List[Dict[str, Any]]] = None
    if payload.portfolio:
        portfolio_dicts = [
            {"symbol": p.symbol, "quantity": p.quantity, "buy_price": p.buy_price}
            for p in payload.portfolio
        ]

    parsed = parse_query(payload.query, context=payload.context or {})
    analysis = reason_about_query(parsed, portfolio=portfolio_dicts)

    stock_report = None
    portfolio_report = None
    market_report = None

    # Attach V4 quant block if we have a primary symbol, to enrich reports/insights.
    primary_symbol = analysis.get("symbol") or parsed.get("primary_symbol")
    if primary_symbol:
        quant_block = quant_analyse(primary_symbol, portfolio=portfolio_dicts)
    else:
        quant_block = None

    if primary_symbol and quant_block:
        v3 = quant_block.get("advisor_v3") or analysis.get("advisor_v3", {})
        stock_report = build_stock_report(primary_symbol, v3, quant_block)

    if analysis.get("portfolio_optimizer") and analysis.get("portfolio_risk"):
        portfolio_report = build_portfolio_report(
            {"optimizer": analysis["portfolio_optimizer"]},
            analysis["portfolio_risk"],
        )
    elif quant_block and quant_block.get("portfolio"):
        portfolio_report = build_portfolio_report(
            quant_block["portfolio"],
            quant_block.get("risk") or {},
        )

    regime_block = analysis.get("market_regime")
    if regime_block:
        market_report = build_market_outlook_report(regime_block)

    insights = generate_insights({**analysis, "advisor_v4": quant_block} if quant_block else analysis)

    response_text = build_chat_response(
        payload.query,
        parsed,
        {**analysis, "advisor_v4": quant_block} if quant_block else analysis,
        stock_report=stock_report,
        portfolio_report=portfolio_report,
        market_report=market_report,
        insights=insights,
    )

    return {
        "source": "advisor_v5",
        "response": response_text,
        "analytics": {
            "intent": parsed.get("intent"),
            "parsed": parsed,
            "analysis": analysis,
            "insights": insights,
        },
    }


@advisor_v5_router.get(
    "/insights",
    summary="Advisor V5 – AI insight feed",
    response_description="High-level AI insights suitable for dashboard panels.",
)
def advisor_v5_insights() -> Dict[str, Any]:
    """
    Lightweight insight feed for dashboards.

    Uses a default symbol (e.g. NIFTY proxy via RELIANCE.NS) and no
    portfolio to generate generic insights.
    """
    # For now, reuse quant_analyse on a liquid large-cap as a proxy.
    symbol = "RELIANCE.NS"
    quant_block = quant_analyse(symbol, portfolio=None)
    v3 = quant_block.get("advisor_v3")
    merged = {"advisor_v3": v3, "advisor_v4": quant_block, "market_regime": quant_block.get("market_regime")}
    insights = generate_insights(merged)
    return {
        "source": "advisor_v5",
        "symbol": symbol,
        "insights": insights,
        "quant_snapshot": quant_block,
    }

