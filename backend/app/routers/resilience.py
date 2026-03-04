"""
Financial Shock Resilience Predictor API.

Resilience module is isolated: lazy imports prevent it from affecting
stock, news, or mutual fund routes.
"""

from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

resilience_router = APIRouter(tags=["resilience"])


class ResilienceRequest(BaseModel):
    """Request body for resilience prediction."""

    income: float = Field(..., gt=0, description="Monthly income")
    monthly_expenses: float = Field(..., gt=0, description="Monthly expenses")
    savings: float = Field(..., ge=0, description="Total liquid savings")
    emi: float = Field(..., ge=0, description="Monthly EMI obligations")
    stock_portfolio_value: Optional[float] = Field(None, ge=0, description="Stock portfolio value (₹)")
    mutual_fund_value: Optional[float] = Field(None, ge=0, description="Mutual fund portfolio value (₹)")
    stock_symbols: Optional[List[str]] = Field(
        None,
        description="Stock symbols for real volatility (e.g. RELIANCE.NS)",
    )
    mf_scheme_codes: Optional[List[str]] = Field(
        None,
        description="MF scheme codes for real volatility (e.g. 119551)",
    )
    expense_history: Optional[List[float]] = Field(
        None,
        description="Last 6–12 months of expenses for expense volatility (e.g. [32000, 35000, 30000, 34000, 36000, 33000])",
    )


@resilience_router.post("/predict-resilience")
def predict_resilience(payload: ResilienceRequest) -> dict:
    """
    Financial shock resilience prediction.

    Computes resilience score, runway months, and risk level from income,
    expenses, savings, and optional portfolio exposure. When stock/MF
    values are provided, integrates market volatility for shock-adjusted metrics.
    """
    # Lazy import: resilience_service is only loaded when this endpoint is hit.
    # Prevents ML/sklearn from affecting startup or other routes.
    try:
        from app.services.resilience_service import predict_resilience as predict_resilience_service
    except Exception as e:
        print("Resilience module import error:", e)
        return {
            "resilience_score": 50,
            "risk_level": "Unknown",
            "status": "fallback_mode",
            "insight": "Resilience module unavailable. Other APIs are unaffected.",
        }

    result = predict_resilience_service(
        income=payload.income,
        monthly_expenses=payload.monthly_expenses,
        savings=payload.savings,
        emi=payload.emi,
        stock_portfolio_value=payload.stock_portfolio_value,
        mutual_fund_value=payload.mutual_fund_value,
        stock_symbols=payload.stock_symbols,
        mf_scheme_codes=payload.mf_scheme_codes,
        expense_history=payload.expense_history,
    )
    return result
