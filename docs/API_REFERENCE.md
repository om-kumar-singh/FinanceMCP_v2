# API Reference – FinanceMCP Backend

This document summarizes the **major API endpoints** exposed by the FastAPI backend of the FinanceMCP platform.

It is intended for developers and researchers who want to integrate with the system, build tools on top of it, or understand how the chat advisor and analytics endpoints are structured.

---

## Base API

The backend is implemented using **FastAPI**.

- **Base URL (example)**:  
  `/api` (or `/` depending on deployment configuration)
- Interactive docs:  
  `/docs` (Swagger UI) and `/redoc` (Redoc, if enabled)

All endpoints described below are relative to the backend base URL.

---

## Chat Advisor API

### `POST /chat` (or `/advisor/chat`)

**Description**  
Conversational AI financial advisor endpoint.  
Handles natural‑language questions about stocks, portfolios, market context, and predictions.

**Example request**

```json
{
  "message": "Should I buy RELIANCE?"
}
```

**Behavior**

Depending on the query, the advisor may return:

- **Stock analysis**
  - Current price, valuation metrics (PE, dividend yield, sector).
  - Simple risk factors and sector context.
- **Technical indicators**
  - RSI, MACD, moving averages, momentum comments.
- **AI predictions**
  - Expected return and predicted price from ensemble models.
  - Confidence labels or scores.
- **Market insights**
  - Market regime summary (bull/bear/sideways).
  - Sector flows and momentum leaders.
- **Portfolio suggestions**
  - High‑level diversification, sector balance, or allocation hints.

Responses are always returned as **formatted text** in a `message` field, with optional structured metadata.

---

## Stock Analysis APIs

### `GET /advisor/v3/analyze`

**Description**  
Detailed stock analysis using the **Advisor V3 reasoning engine**.

V3 combines:

- Prediction outputs (expected return, volatility).
- Technical indicators.
- Market and sector context.
- Basic sentiment and volume heuristics.

**Typical usage**

- Deeper analysis for a single stock, e.g. factor scores and narrative explanation.
- Programmatic access to the same data that powers some of the chat advisor’s insights.

Request/response schemas are documented in the FastAPI OpenAPI spec at `/docs`.

---

## Quant Analysis APIs

### `GET /advisor/v4/quant-analysis`

**Description**  
Advanced quant analysis driven by **Advisor V4** modules, including:

- Market regime detection (bull/bear/sideways + volatility level).
- Strategy ensemble evaluations (momentum, mean reversion, trend‑following, volatility breakout).
- Smart‑money / institutional activity heuristics.
- Portfolio risk metrics and optimizer outputs (when a portfolio is provided).

**Use cases**

- Building advanced dashboards with strategy‑level views.
- Research and back‑testing support (when combined with historical data).
- Feeding higher‑level tools (e.g. AI assistants, MCP tools) with rich quant features.

---

## Portfolio Analysis API

### `POST /portfolio/analyze`

**Description**  
Analyzes **portfolio risk and diversification** using backend portfolio intelligence modules.

**Example input**

```json
{
  "portfolio": {
    "RELIANCE": 0.4,
    "TCS": 0.3,
    "HDFCBANK": 0.3
  }
}
```

**Behavior**

The endpoint typically returns:

- Sector and stock‐level allocation breakdowns.
- Simple volatility or risk estimations.
- Diversification and concentration measures.
- Narrative commentary that can be surfaced in UI or advisor responses.

This API is often called directly by the frontend for portfolio views, and indirectly by the chat advisor for “analyze my portfolio” intents.

---

## Comparison API

### `POST /compare`

**Description**  
Compares **multiple stocks** based on valuation and fundamentals.

Typical behavior:

- Accepts a list of stock symbols (e.g. `["TCS", "INFY", "HCLTECH", "TECHM"]`).
- Fetches for each symbol:
  - price
  - PE ratio
  - dividend yield
  - sector
  - market cap.
- Builds a comparison table and identifies leaders, e.g.:
  - **valuation leader** (lowest PE)
  - **income leader** (highest dividend yield)
  - **size leader** (largest market cap).

This is the same information the chat advisor uses for multi‑stock comparison queries like “Compare TCS INFY HCLTECH and TECHM”.

---

## Market Insights API

### `GET /advisor/insights`

**Description**  
Provides AI‑generated **market insights** suitable for dashboards or news‑style feeds.

Insights can include:

- High‑level market regime commentary.
- Sector rotation and flow observations.
- Top AI‑predicted names or risk warnings.
- Short narrative summaries for distribution in UI cards or emails.

This endpoint is often used to populate a “Today’s Insights” panel in the frontend.

---

## Data Sources

The backend builds on top of several external data services:

- **yfinance**
  - Stock quotes and OHLCV history.
  - Basic fundamentals (PE, dividend yield, sector, market cap).
  - Index and sector data.
- **Macro indicators**
  - GDP growth series (e.g. via World Bank APIs).
  - Inflation / CPI time series.
  - Repo rate and other RBI policy rates.
- **Mutual fund APIs**
  - NAV series and scheme metadata for Indian mutual funds.
- **News APIs** (if configured)
  - Market and macro headlines, used for basic sentiment overlay.

Exact endpoints and authentication keys are set via environment variables and may differ between deployments.

---

## Error Handling

The API follows conventional HTTP semantics:

- **`400 Bad Request`**
  - Invalid or missing parameters (e.g. malformed JSON, invalid symbol list, or incorrect field types).
  - The response body typically includes a brief error message and details about validation failures.

- **`404 Not Found`**
  - Data for a specific symbol or resource could not be found.
  - For example, requesting analysis for an unsupported ticker.

- **`500 Internal Server Error`**
  - Unexpected server‑side error or upstream data issue.
  - The system logs details on the backend; the client receives a generic error message.

Advisor endpoints are designed to **fail gracefully** whenever possible, returning explanatory text such as:

- “I could not identify the stock symbol. Please specify the company.”
- “Comparison data is temporarily unavailable. Please try again.”

rather than raw stack traces or unformatted JSON.

---

## Notes for Integrators

- Always refer to the live **OpenAPI schema** at `/docs` for authoritative request/response models.
- Some endpoints are optional and may be disabled in certain deployments (e.g. V2/V3/V4 advisor routes).
- Rate‑limiting and authentication are environment‑specific and should be configured at the deployment level.

For more on the architectural context behind these APIs, see `docs/ARCHITECTURE.md` and `docs/AI_ADVISOR.md`.

