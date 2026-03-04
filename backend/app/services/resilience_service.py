"""
Financial Shock Resilience Predictor service.

Computes resilience score, runway, and risk level from income, expenses,
savings, and optional portfolio exposure. Integrates with stock/MF data
for volatility-based adjustments and macro news sentiment.
"""

import os
from typing import Any, Optional, Tuple

import requests
import yfinance as yf

from app.services.news_service import get_market_news


def _get_ml_prediction(features: list[float]) -> Optional[float]:
    """
    Lazy-import ML module and predict. Returns None if sklearn unavailable or ML fails.
    ML training only runs when predict_resilience is called and model file does not exist.
    """
    try:
        import sklearn  # noqa: F401
    except ImportError:
        return None
    try:
        from app.ml.resilience_model import predict_resilience as ml_predict
        return ml_predict(features)
    except Exception as e:
        print("ML module error:", e)
        return None

# Default daily volatility (std of daily returns) when no symbols provided.
# ~0.012 ≈ 19% annualized for Indian equities.
DEFAULT_PORTFOLIO_VOLATILITY = 0.012

MF_API_BASE = os.getenv("MF_API_BASE_URL", "https://api.mfapi.in/mf")


def _get_stock_daily_returns_volatility(symbols: list[str], days: int = 35) -> Optional[float]:
    """
    Compute std of daily returns for given stock symbols using yfinance.
    Returns mean volatility across symbols, or None on failure.
    """
    if not symbols:
        return None

    symbols = [s.strip().upper() for s in symbols if s and str(s).strip()]
    if not symbols:
        return None

    volatilities: list[float] = []
    for symbol in symbols[:5]:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=f"{days}d")
        except Exception:
            continue
        if hist is None or hist.empty or len(hist) < 5:
            continue
        try:
            returns = hist["Close"].pct_change().dropna()
            if returns.empty or len(returns) < 3:
                continue
            vol = float(returns.std())
            volatilities.append(vol)
        except Exception:
            continue

    if not volatilities:
        return None
    return sum(volatilities) / len(volatilities)


def _get_mf_daily_returns_volatility(scheme_codes: list[str], max_points: int = 35) -> Optional[float]:
    """
    Compute std of daily NAV returns for given MF scheme codes.
    Returns None on failure.
    """
    if not scheme_codes:
        return None

    all_returns: list[float] = []
    for code in scheme_codes[:5]:
        code = str(code).strip()
        if not code:
            continue
        try:
            url = f"{MF_API_BASE}/{code}"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            continue

        nav_data = data.get("data")
        if not isinstance(nav_data, list) or len(nav_data) < 3:
            continue

        navs: list[tuple[str, float]] = []
        for item in nav_data[:max_points]:
            if not isinstance(item, dict):
                continue
            nav_str = item.get("nav")
            date_val = item.get("date")
            try:
                n = float(nav_str)
                if date_val and n > 0:
                    navs.append((str(date_val), n))
            except (TypeError, ValueError):
                continue

        if len(navs) < 3:
            continue

        for i in range(1, len(navs)):
            prev = navs[i - 1][1]
            curr = navs[i][1]
            if prev and prev > 0:
                ret = (curr - prev) / prev
                all_returns.append(ret)

    if len(all_returns) < 3:
        return None

    import statistics
    return statistics.stdev(all_returns)


def _runway_to_base_score(runway_months: float) -> float:
    """Emergency fund scale: runway months → base score."""
    if runway_months < 1:
        return 10
    if runway_months < 3:
        return 30
    if runway_months < 6:
        return 60
    if runway_months < 12:
        return 80
    return 95


def _classify_risk(score: float) -> str:
    """Classify risk level from final resilience score."""
    if score >= 75:
        return "Strong"
    if score >= 50:
        return "Moderate"
    if score >= 25:
        return "Vulnerable"
    return "High Risk"


def _build_insight(
    risk_level: str,
    runway_months: float,
    adjusted_runway: Optional[float],
    emi_ratio: float,
    has_portfolio: bool,
) -> str:
    """Build a short explanatory insight string."""
    parts = []
    if risk_level == "Strong":
        parts.append("Your finances show strong resilience to shocks.")
    elif risk_level == "Moderate":
        parts.append("Moderate resilience. Consider building a larger emergency buffer.")
    elif risk_level == "Vulnerable":
        parts.append("Your runway is limited. Prioritize increasing savings.")
    else:
        parts.append("High risk. Focus on reducing expenses and increasing runway.")

    if adjusted_runway is not None and adjusted_runway < runway_months and has_portfolio:
        parts.append("A 20% market shock would reduce your runway.")
    if emi_ratio > 0.4:
        parts.append("High EMI ratio may strain cash flow during shocks.")
    return " ".join(parts)


def _compute_macro_sentiment_risk(
    max_items: int = 10,
) -> Tuple[int, int]:
    """
    Derive a simple macro risk adjustment from recent market news.

    Returns:
        macro_risk_factor, negative_news_count
    """
    negative_keywords = [
        "crash",
        "recession",
        "layoff",
        "inflation spike",
        "bankruptcy",
        "default",
        "slowdown",
        "market fall",
        "economic crisis",
        "bear market",
    ]

    try:
        # Reuse existing market news service; NSE gives broad Indian market news.
        items = get_market_news("NSE") or []
    except Exception:
        return 0, 0

    headlines = [str(item.get("title") or "") for item in items[:max_items]]
    if not headlines:
        return 0, 0

    sentiment_score = 0
    for title in headlines:
        lower = title.lower()
        for kw in negative_keywords:
            if kw in lower:
                sentiment_score += 1
                break

    if sentiment_score >= 5:
        macro_risk_factor = 15
    elif 3 <= sentiment_score <= 4:
        macro_risk_factor = 10
    elif 1 <= sentiment_score <= 2:
        macro_risk_factor = 5
    else:
        macro_risk_factor = 0

    return macro_risk_factor, sentiment_score


def simulate_financial_shocks(
    savings: float,
    monthly_expenses: float,
    portfolio_value: float,
    portfolio_volatility: float,
    income: float,
    emi: float,
    iterations: int = 500,
    runway_months_fallback: Optional[float] = None,
) -> dict[str, Optional[float]]:
    """
    Monte Carlo simulation of financial survival under market and income shocks.

    Returns a dict with median_survival_months, worst_case_survival_months,
    and survival_probability_6_months (percentage of runs with > 6 months runway).
    """
    import random
    import statistics

    try:
        if monthly_expenses <= 0 or iterations <= 0:
            raise ValueError("monthly_expenses must be positive for simulation.")

        results: list[float] = []

        # Clamp iterations to avoid runaway CPU usage.
        n_iter = min(max(iterations, 1), 1000)

        emergency_probability = 0.25
        for _ in range(n_iter):
            # Market shock on portfolio
            if portfolio_volatility > 0:
                market_return = random.normalvariate(0.0, portfolio_volatility)
            else:
                market_return = 0.0
            portfolio_change = portfolio_value * market_return

            # Job loss shock
            job_loss = random.random()
            if job_loss < 0.1:
                months_without_income = random.randint(3, 6)
            else:
                months_without_income = 0

            available_funds = savings + portfolio_change
            if months_without_income > 0:
                available_funds -= monthly_expenses * months_without_income

            # Emergency expense shock (medical, travel, car repair, family support)
            if random.random() < emergency_probability:
                emergency_cost = random.uniform(
                    monthly_expenses * 1,
                    monthly_expenses * 3,
                )
                available_funds -= emergency_cost

            survival_months = available_funds / monthly_expenses
            results.append(survival_months)

        if not results:
            raise ValueError("No simulation results.")

        median_survival = float(statistics.median(results))
        worst_case_survival = float(min(results))
        survival_probability = (
            sum(1 for v in results if v > 6.0) / len(results) * 100.0
        )

        return {
            "median_survival_months": round(median_survival, 2),
            "worst_case_survival_months": round(worst_case_survival, 2),
            "survival_probability_6_months": round(survival_probability, 2),
            "emergency_shock_probability": emergency_probability,
        }
    except Exception:
        # Fall back gracefully with runway-based defaults.
        r = runway_months_fallback or 0
        return {
            "median_survival_months": round(r, 2) if r else None,
            "worst_case_survival_months": round(r * 0.7, 2) if r else None,
            "survival_probability_6_months": 60.0,
            "emergency_shock_probability": 0.25,
        }


def predict_resilience(
    income: float,
    monthly_expenses: float,
    savings: float,
    emi: float,
    stock_portfolio_value: Optional[float] = None,
    mutual_fund_value: Optional[float] = None,
    stock_symbols: Optional[list[str]] = None,
    mf_scheme_codes: Optional[list[str]] = None,
    expense_history: Optional[list[float]] = None,
) -> dict[str, Any]:
    """
    Compute financial shock resilience score and metrics.

    Args:
        income: Monthly income
        monthly_expenses: Monthly expenses
        savings: Total liquid savings
        emi: Monthly EMI obligations
        stock_portfolio_value: Optional stock portfolio value (₹)
        mutual_fund_value: Optional mutual fund value (₹)
        stock_symbols: Optional symbols to fetch real stock volatility
        mf_scheme_codes: Optional scheme codes to fetch real MF volatility

    Returns:
        Dict with resilience_score, runway_months, adjusted_runway_after_market_shock,
        portfolio_volatility, risk_level, insight.
    """
    try:
        return _predict_resilience_impl(
            income, monthly_expenses, savings, emi,
            stock_portfolio_value, mutual_fund_value,
            stock_symbols, mf_scheme_codes,
            expense_history,
        )
    except Exception as e:
        print("Resilience engine failure:", e)
        return _fallback_response()


def _compute_expense_volatility(
    expense_history: Optional[list[float]], monthly_expenses: float
) -> float:
    """
    Expense volatility: std dev of expense_history if provided (6–12 months),
    else estimated as monthly_expenses * 0.1.
    """
    if expense_history and len(expense_history) >= 2:
        vals = [float(x) for x in expense_history if x is not None and isinstance(x, (int, float))]
        if len(vals) >= 2:
            import statistics
            return float(statistics.stdev(vals))
    return monthly_expenses * 0.1


def _predict_resilience_impl(
    income: float,
    monthly_expenses: float,
    savings: float,
    emi: float,
    stock_portfolio_value: Optional[float],
    mutual_fund_value: Optional[float],
    stock_symbols: Optional[list[str]],
    mf_scheme_codes: Optional[list[str]],
    expense_history: Optional[list[float]],
) -> dict[str, Any]:
    """Inner implementation; never raises to caller."""
    request_data = {
        "income": income,
        "monthly_expenses": monthly_expenses,
        "savings": savings,
        "emi": emi,
        "stock_portfolio_value": stock_portfolio_value,
        "mutual_fund_value": mutual_fund_value,
        "expense_history": expense_history,
    }
    print("Resilience Inputs:", request_data)

    # Prevent division by zero
    income = max(float(income or 0), 1)
    monthly_expenses = max(float(monthly_expenses or 0), 1)
    savings = float(savings or 0)

    runway_months = savings / monthly_expenses
    expense_volatility = _compute_expense_volatility(expense_history, monthly_expenses)

    try:
        savings_ratio = savings / income
        expense_ratio = monthly_expenses / income
        emi_ratio = emi / income

        stock_val = stock_portfolio_value or 0
        mf_val = mutual_fund_value or 0
        portfolio_value = stock_val + mf_val
        has_portfolio = portfolio_value > 0

        adjusted_runway: Optional[float] = None
        if portfolio_value == 0:
            portfolio_volatility = 0.02
        else:
            vol_stock = _get_stock_daily_returns_volatility(stock_symbols or []) if stock_symbols else None
            vol_mf = _get_mf_daily_returns_volatility(mf_scheme_codes or []) if mf_scheme_codes else None

            if vol_stock is not None and vol_mf is not None and portfolio_value > 0:
                w_stock = stock_val / portfolio_value
                w_mf = mf_val / portfolio_value
                portfolio_volatility = w_stock * vol_stock + w_mf * vol_mf
            elif vol_stock is not None and stock_val > 0 and mf_val == 0:
                portfolio_volatility = vol_stock
            elif vol_mf is not None and mf_val > 0 and stock_val == 0:
                portfolio_volatility = vol_mf
            else:
                portfolio_volatility = DEFAULT_PORTFOLIO_VOLATILITY

            shock_loss = portfolio_value * 0.20
            adjusted_savings = max(0.0, savings - shock_loss)
            adjusted_runway = adjusted_savings / monthly_expenses

        # Monte Carlo financial shock simulation (needed for shock_penalty)
        sim_result = simulate_financial_shocks(
            savings=savings,
            monthly_expenses=monthly_expenses,
            portfolio_value=portfolio_value,
            portfolio_volatility=portfolio_volatility,
            income=income,
            emi=emi,
            runway_months_fallback=runway_months,
        )
        survival_prob = sim_result.get("survival_probability_6_months")

        # Base score from emergency fund scale
        base_score = _runway_to_base_score(runway_months)

        # Limited penalties
        portfolio_penalty = min(portfolio_volatility * 50, 15)
        emi_penalty = 10 if emi_ratio > 0.4 else 0
        if isinstance(survival_prob, (int, float)):
            if survival_prob < 40:
                shock_penalty = 10
            elif survival_prob < 60:
                shock_penalty = 5
            else:
                shock_penalty = 0
        else:
            shock_penalty = 0

        final_score = base_score - portfolio_penalty - emi_penalty - shock_penalty
        final_score = max(final_score, 10)

        # Macro sentiment (capped) as small adjustment
        macro_risk_factor, negative_news_count = _compute_macro_sentiment_risk()
        final_score = final_score - min(macro_risk_factor, 10)
        final_score = max(final_score, 10)

        # Machine learning-based resilience score (lazy import, sklearn guard)
        survival_feature = float(survival_prob) if isinstance(survival_prob, (int, float)) else 50.0
        # Normalize expense_volatility for ML: use ratio to monthly_expenses to keep scale ~0.01–0.2
        exp_vol_ratio = expense_volatility / monthly_expenses if monthly_expenses > 0 else 0.1
        features = [
            savings_ratio,
            expense_ratio,
            emi_ratio,
            portfolio_volatility,
            exp_vol_ratio,
            float(macro_risk_factor),
            survival_feature,
        ]
        ml_score = _get_ml_prediction(features)
        if ml_score is not None:
            final_score = (final_score * 0.6) + (ml_score * 0.4)
        else:
            ml_score = final_score  # for display when ML unavailable

        final_score = round(max(min(final_score, 100), 0), 2)

        risk_level = _classify_risk(final_score)
        print("Portfolio Value:", portfolio_value)
        print("Final Score:", final_score)

        insight = _build_insight(
            risk_level, runway_months, adjusted_runway, emi_ratio, has_portfolio
        )

        result: dict[str, Any] = {
            "resilience_score": final_score,
            "combined_resilience_score": final_score,
            "ml_resilience_score": ml_score,
            "runway_months": round(runway_months, 2),
            "risk_level": risk_level,
            "insight": insight,
        }

        if has_portfolio and adjusted_runway is not None:
            result["adjusted_runway_after_market_shock"] = round(adjusted_runway, 2)
        if has_portfolio:
            result["portfolio_volatility"] = round(portfolio_volatility, 4)

        # New research-grade metrics
        result["expense_volatility"] = round(expense_volatility, 2)
        result["emergency_shock_probability"] = 0.25

        # Always include macro sentiment fields so clients can inspect behaviour.
        result["macro_sentiment_risk"] = macro_risk_factor
        result["negative_news_count"] = negative_news_count
        if macro_risk_factor > 0:
            result["news_based_adjustment"] = "High macroeconomic stress detected"

        # Include Monte Carlo simulation outputs
        result["median_survival_months"] = sim_result.get("median_survival_months")
        result["worst_case_survival_months"] = sim_result.get(
            "worst_case_survival_months"
        )
        result["survival_probability_6_months"] = sim_result.get(
            "survival_probability_6_months"
        )

        return result
    except Exception as e:
        print("Resilience Predictor Error (partial fallback):", str(e))
        try:
            return _partial_resilience_response(runway_months, income, monthly_expenses)
        except Exception:
            return _fallback_response()


def _partial_resilience_response(
    runway_months: float, income: float, monthly_expenses: float
) -> dict[str, Any]:
    """Return minimal JSON on partial failure."""
    fallback_score = min(100, max(0, runway_months * 10))
    risk_level = _classify_risk(fallback_score)
    return {
        "status": "partial_success",
        "resilience_score": round(fallback_score, 2),
        "risk_level": risk_level,
        "runway_months": round(runway_months, 2),
        "insight": "Partial result due to processing error. Please retry.",
    }


def _fallback_response() -> dict[str, Any]:
    """Return minimal JSON when resilience engine fails completely."""
    return {
        "resilience_score": 50,
        "risk_level": "Unknown",
        "status": "fallback_mode",
    }
