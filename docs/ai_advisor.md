## AI Advisor (V1–V5) — Architecture & Endpoints

This project includes multiple “advisor” layers. The UI currently uses the chat-based advisor (V1), while V2–V5 are optional additive endpoints designed for richer analytics and future dashboards.

### Live Market Data (shared across advisor versions)

The advisor stack **reuses the existing live market data services**:

- **Stocks & OHLCV**: `backend/app/services/stock_service.py` (yfinance)
- **News headlines**: `backend/app/services/news_service.py` (yfinance `Ticker.news`)
- **Sector performance**: `backend/app/services/sector_service.py` (yfinance)
- **Portfolio enrichment**: `backend/app/services/portfolio_service.py` (yfinance download + sector allocation)

No new market data providers are introduced in advisor versions V2–V5.

---

## V1 — Dashboard “AI Advisor” (Chat)

### What it is

The dashboard’s **AI Advisor tab** renders a chat UI that calls the backend chat endpoint and returns structured responses formatted into markdown.

### Frontend

- **UI**: `frontend/src/components/Chat.jsx`
- **Dashboard tab**: `frontend/src/pages/Dashboard.jsx`
- **API client**: `frontend/src/services/api.js` → `POST /chat`

### Backend

- **Routes**: `backend/app/routes/query_routes.py`
  - `POST /chat`
  - `POST /ask`
- **Logic**: `backend/app/services/query_service.py`
  - Rule/intent based routing (stock price, RSI/MACD, comparisons, buy/hold style guidance, market news, etc.)

### Response pattern

V1 responses follow:

```json
{
  "query": "user query",
  "source": "stock_analysis | technical_analysis | market_news | ...",
  "result": { "...": "..." }
}
```

This shape is intentionally preserved in V2–V4, and V5 provides a conversational wrapper.

---

## V2 — Enhanced analytics endpoints (optional)

### Endpoints

- `POST /advisor/v2/stock`
- `POST /advisor/v2/portfolio`

### Purpose

V2 adds a structured layer for:

- Ensemble-style forecasting heuristics
- Signal scoring
- Portfolio risk metrics (volatility / Sharpe / diversification score)
- Natural-language explanation blocks

### Key modules

- `backend/app/services/advisor_v2/prediction_engine.py`
- `backend/app/services/advisor_v2/signal_scoring.py`
- `backend/app/services/advisor_v2/portfolio_risk.py`
- `backend/app/services/advisor_v2/explanation_engine.py`
- `backend/app/routes/advisor_v2_routes.py`

---

## V3 — Reasoning layer (ChatGPT-style analyst output, optional)

### Endpoint

- `POST /advisor/v3/analyze`

### Purpose

V3 combines V2 outputs with:

- Market context (NIFTY regime proxy + sector strength)
- News sentiment approximation
- Multi-factor stock scoring + explanation
- Structured “institutional” analytics fields for future dashboards

### Key modules

- `backend/app/services/advisor_v3/market_context.py`
- `backend/app/services/advisor_v3/reasoning_engine.py`
- `backend/app/routes/advisor_v3_routes.py`

---

## V4 — Quantitative layer (strategies, optimizer, VaR/ES, smart money, optional)

### Endpoint

- `POST /advisor/v4/quant-analysis`

### Purpose

V4 adds hedge-fund style components:

- Market regime detection (bull/bear/sideways + volatility level)
- Strategy ensemble (momentum, mean reversion, trend-following, volatility breakout)
- Smart money/institutional flow heuristics (volume spike + price move patterns)
- Portfolio optimizer (Markowitz-style approximation)
- Advanced risk metrics (VaR, expected shortfall, beta, drawdown)

### Key modules

- `backend/app/services/advisor_v4/regime_detection.py`
- `backend/app/services/advisor_v4/strategy_engine.py`
- `backend/app/services/advisor_v4/smart_money_tracker.py`
- `backend/app/services/advisor_v4/portfolio_optimizer.py`
- `backend/app/services/advisor_v4/risk_engine.py`
- `backend/app/services/advisor_v4/quant_engine.py`
- `backend/app/routes/advisor_v4_routes.py`

---

## V5 — Conversational Financial Intelligence Layer (optional)

### Endpoints

- `POST /advisor/chat` (conversational)
- `GET /advisor/insights` (dashboard insight feed)

### Purpose

V5 provides:

- Natural language parsing → intent/entity extraction
- Routing to the correct engines (V3/V4 + portfolio optimizer + regime detector)
- Insight generation and report-style summaries
- Conversational responses suitable for a ChatGPT-style assistant

### Key modules

- `backend/app/services/advisor_v5/query_parser.py`
- `backend/app/services/advisor_v5/financial_reasoner.py`
- `backend/app/services/advisor_v5/insight_engine.py`
- `backend/app/services/advisor_v5/report_generator.py`
- `backend/app/services/advisor_v5/response_generator.py`
- `backend/app/routes/advisor_v5_routes.py`

---

## Quick test payloads

### V5 chat

```json
{
  "query": "Should I buy RELIANCE right now?",
  "context": { "last_symbol": "RELIANCE.NS" }
}
```

### V4 quant

```json
{
  "symbol": "RELIANCE.NS",
  "portfolio": [
    { "symbol": "RELIANCE.NS", "quantity": 10, "buy_price": 2000 },
    { "symbol": "TCS.NS", "quantity": 5, "buy_price": 3500 }
  ]
}
```

