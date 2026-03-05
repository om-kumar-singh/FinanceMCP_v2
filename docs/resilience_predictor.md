## Resilience Predictor — Financial Shock Resilience (ML + Simulation)

The Resilience Predictor is a separate feature from the stock “AI Advisor” chat. It estimates how resilient a user’s finances are to shocks (market drawdowns, job loss, emergency expenses).

### Where it lives

#### Backend

- **Route**: `backend/app/routers/resilience.py`
  - `POST /predict-resilience`
- **Service**: `backend/app/services/resilience_service.py`
  - Core scoring logic
  - Market volatility adjustments (optional)
  - Monte Carlo shock simulation
  - News-based macro stress heuristic
  - Optional ML blending
- **ML model**: `backend/app/ml/resilience_model.py`
  - RandomForestRegressor trained on synthetic data (stored as a pickle)
- **Optional LLM tips**: `backend/app/services/gemini_service.py`
  - If `GEMINI_API_KEY` is configured, generates scenario-based recommendations.

#### Frontend

- **Page**: `frontend/src/pages/ResiliencePredictor.jsx`
  - Form inputs and result visualization

---

## Live data usage (existing sources)

The predictor reuses existing data sources already implemented in the project:

- **Stock volatility** (optional): yfinance history for provided `stock_symbols`
- **Mutual fund volatility** (optional): `mfapi.in` NAV series for provided `mf_scheme_codes`
- **News-based macro stress**: yfinance market news via `backend/app/services/news_service.py`

---

## API: `POST /predict-resilience`

### Request body (high level)

- Required:
  - `income` (monthly)
  - `monthly_expenses`
  - `savings`
  - `emi`
- Optional:
  - `stock_portfolio_value`, `mutual_fund_value`
  - `stock_symbols` (for real volatility)
  - `mf_scheme_codes` (for real volatility)
  - `expense_history` (for expense volatility)
  - `profile` (for personalised recommendations)

### Response (key fields)

- **Core**:
  - `resilience_score` / `combined_resilience_score` (0–100)
  - `risk_level` (Strong/Moderate/Vulnerable/High Risk)
  - `runway_months`
- **Shock / scenario**:
  - `adjusted_runway_after_market_shock` (when portfolio values provided)
  - Monte Carlo outputs:
    - `median_survival_months`
    - `worst_case_survival_months`
    - `survival_probability_6_months`
- **Macro sentiment**:
  - `macro_sentiment_risk`
  - `negative_news_count`
- **Recommendations**:
  - `recommendations`: `normal`, `market_crash`, `job_loss`, `emergency`
  - `recommendation_source`: `gemini` or `gemini_unavailable`

---

## How it works (high level)

1. **Base runway & ratios**
   - runway months = savings / monthly_expenses
   - EMI burden ratio = emi / income

2. **Volatility-aware adjustment** (optional)
   - Estimates portfolio volatility using market data and adjusts runway under a simulated drawdown.

3. **Monte Carlo shock simulation**
   - Simulates market shocks + job loss + emergency expenses to estimate survival distribution.

4. **Macro stress adjustment**
   - Looks for negative keywords in recent market headlines and applies a capped risk adjustment.

5. **ML blend (optional)**
   - If `scikit-learn` is available, blends in a RandomForest score.

6. **Recommendations**
   - If Gemini is configured, returns scenario tips; otherwise returns empty scenario lists (core metrics still work).

