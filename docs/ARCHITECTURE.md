# System Architecture – FinanceMCP

## System Architecture Overview

FinanceMCP is a modular **AI financial intelligence platform** that combines:

- **AI stock advisor** – conversational assistant for stocks, technicals, and predictions.
- **Financial resilience predictor** – estimates how well a household can withstand financial shocks.
- **Portfolio analysis** – risk, diversification, and allocation analytics.
- **Quant prediction engine** – ensemble models for expected returns and risk.
- **Market regime detection** – identifies bullish, bearish, or sideways environments.

The system brings together:

- **Machine learning** – ensemble regressors, scoring models, and ML‑enhanced risk metrics.
- **Quantitative finance** – volatility modeling, regime detection, portfolio optimization.
- **Technical analysis** – RSI, MACD, moving averages, Bollinger Bands, and momentum signals.
- **API‑based market data** – primarily via `yfinance`, plus macro and fund data providers.

All of these modules are orchestrated through a layered advisor architecture exposed over a **FastAPI** backend and a **React + Vite** frontend.

---

## High‑Level Architecture

At a high level, the platform can be visualized as:

```text
Frontend (React + Vite)
        ↓
API Layer (FastAPI routes)
        ↓
Service Layer (business logic)
        ↓
Quant / AI Engines (advisor_v2–v5)
        ↓
Market Data & External APIs
```

- **Frontend (React + Vite)**  
  Implements the dashboard UI, chat interface, charts, watchlists, and forms for portfolio and resilience analysis.

- **API Layer (FastAPI routes)**  
  Exposes HTTP endpoints (e.g. `/advisor/chat`, `/advisor/v3/analyze`, `/portfolio/analyze`, `/predict-resilience`) and maps them to service functions.

- **Service Layer (business logic)**  
  Contains application logic in `backend/app/services`, coordinating data fetches, technical calculations, ML models, and response shaping.

- **Quant / AI engines**  
  Advisor generations V2–V5 (prediction engine, reasoning engine, quant engine, conversational layer) and resilience prediction models.

- **Market Data APIs**  
  yfinance for equities and indices, macro data APIs for GDP, inflation, and repo rate, as well as optional news and mutual fund APIs.

---

## Advisor Architecture Layers

The AI advisor is implemented as a series of layers, each responsible for a specific part of the pipeline from user query to response.

### Layer 1 — Query Router & Intent Parser

**Files involved:**

- `backend/app/services/chat_advisor_service.py`
- `backend/app/services/chat_intent_classifier.py`
- `backend/app/services/advisor_v5/query_parser.py`
- `backend/app/services/advisor_v5/symbol_dictionary.py`

**Responsibilities:**

- Parse and understand user questions in natural language.
- Extract **stock symbols**, sectors, and relevant entities from the query.
- Detect **intent**, e.g.:
  - stock prediction
  - comparison
  - buy/hold decision
  - portfolio analysis
  - market regime request
  - AI stock screening.
- Route requests to the correct **services and advisor layers** (V2, V3, V4, or resilience/portfolio modules).

This layer is the “front door” of the advisor: every chat request passes through it before touching data or models.

---

### Layer 2 — Market Data Layer

**Files:**

- `backend/app/services/market_data_service.py`
- `backend/app/services/stock_service.py`
- `backend/app/services/news_service.py`
- `backend/app/services/macro_service.py` (or equivalent macro aggregation service)

**Responsibilities:**

- Fetch **current stock prices** and intraday quotes.
- Retrieve **historical OHLCV data** for technical indicators and models.
- Fetch **macro indicators** such as:
  - GDP growth
  - inflation / CPI
  - repo rate and other policy rates.
- Fetch **market news** and headlines for sentiment and macro stress heuristics.

**Data source:**

- Primary: **`yfinance`** (Yahoo Finance) for equities, indices, and basic fundamentals.
- Additional HTTP APIs for mutual funds and macro data.

This layer ensures that upstream layers always receive consistent, normalized data structures.

---

### Layer 3 — Technical Indicator Engine

**Indicators implemented (conceptually):**

- **RSI (Relative Strength Index)**
- **MACD (Moving Average Convergence Divergence)** and signal line
- **Moving averages** (e.g. SMA20, SMA50, SMA200)
- **Bollinger Bands** and other volatility‑band‑style indicators

**File:**

- `backend/app/services/stock_service.py`

**Usage:**

These indicators are reused by both:

- The **chat advisor** – for user queries like “What does RSI say about INFY?” and “Is this stock overbought?”.
- The **prediction engine** – as input features for ensemble models and scoring logic in Advisor V2–V4.

The technical engine sits between raw OHLCV data and higher‑level analytics, providing a library of standard trading indicators.

---

### Layer 4 — Prediction Engine

**Files:**

- `backend/app/services/advisor_v2/prediction_engine.py`
- `backend/app/services/advisor_v2/signal_scoring.py`
- `backend/app/services/prediction_ranking_service.py`

**Responsibilities:**

- Predict **expected return** for a stock over a given horizon (intraday, short, medium).
- Estimate **volatility and confidence** of predictions.
- Rank stocks by **AI forecast** for screener‑style queries (e.g. “Which stocks have the highest predicted growth?”).

**Ensemble structure (conceptual):**

- **Sequence model**  
  A model that ingests recent price/indicator sequences (e.g. RNN/LSTM or temporal features) to capture short‑term dynamics.
- **Tree‑based model**  
  Gradient boosting or random forests on top of engineered features (technical indicators, returns, volatility) for tabular robustness.

The prediction engine combines models into a **blended forecast** with an expected return, predicted price, and confidence score, which are then consumed by reasoning and quant layers.

---

### Layer 5 — Advisor Reasoning Engine

**Files:**

- `backend/app/services/advisor_v3/reasoning_engine.py`
- `backend/app/services/advisor_v3/market_context.py`

**Responsibilities:**

- Combine:
  - predictions from the V2 engine,
  - market and sector context,
  - technical indicators,
  - simple sentiment and volume signals.
- Analyze **sector context** and relative strength.
- Evaluate **risk factors**, such as:
  - volatility level,
  - concentration in a sector,
  - regime‑specific hazards.
- Generate **recommendation scores** and explanations, such as:
  - factor breakdowns (prediction, momentum, sentiment, trend, volatility),
  - textual rationales for BUY / HOLD / AVOID‑style outputs.

This layer acts like an “AI analyst,” turning raw numerical outputs into structured reasoning that can be surfaced to users.

---

### Layer 6 — Quant Engine

**Files:**

- `backend/app/services/advisor_v4/quant_engine.py`
- `backend/app/services/advisor_v4/regime_detection.py`
- `backend/app/services/advisor_v4/strategy_engine.py`
- `backend/app/services/advisor_v4/smart_money_tracker.py`
- `backend/app/services/advisor_v4/risk_engine.py`
- `backend/app/services/advisor_v4/portfolio_optimizer.py`

**Responsibilities:**

- **Detect market regimes**
  - Classify index behavior into bull / bear / sideways regimes.
  - Estimate volatility levels and trend strength.
- **Evaluate trading strategies**
  - Momentum, mean reversion, volatility breakout, and trend‑following logic.
  - Strategy scorecards and composite signals.
- **Detect institutional/smart‑money activity**
  - Unusual volume and price/volume patterns.
  - Accumulation / distribution style metrics.
- **Optimize portfolios**
  - Markowitz‑style portfolio optimization approximations.
  - Risk/return trade‑off and diversification metrics.

The quant engine is used both **directly** (via `/advisor/v4/quant-analysis`) and **indirectly** (inside the chat advisor for regime and risk commentary).

---

### Layer 7 — Response Generation

**Files:**

- `backend/app/services/advisor_v5/response_generator.py`
- `backend/app/services/advisor_v5/report_generator.py`
- `backend/app/services/advisor_v5/insight_engine.py`

**Responsibilities:**

- Take structured analysis from earlier layers and convert it into:
  - human‑readable **chat responses**,
  - **comparison tables** (multi‑stock comparisons),
  - **reports** (stock analysis, portfolio reports, market outlook),
  - **insight feeds** for dashboards.
- Guarantee that chat replies are **formatted text**, not raw JSON.
- Provide consistent **sectioned output**, e.g.:
  - Summary
  - Interpretation
  - Risk Factors
  - Conclusion

The response generator is the last step before data reaches the frontend; it determines how insights are presented to end users and AI tools.

---

## Request Flow Example

Consider the user question:

> “Should I buy RELIANCE?”

The flow is:

1. **Frontend chat UI (React + Vite)**
   - User types the question into the chat box.
   - The frontend sends a `POST /advisor/chat` (or equivalent `/chat`) request with the query text and any prior context.

2. **/chat API route (FastAPI)**
   - The route receives the HTTP request and forwards it to `chat_advisor_service`.

3. **`chat_advisor_service.py`**
   - Orchestrates the advisor flow.
   - Calls the **intent classifier** to determine that this is a `buy_decision` for `RELIANCE`.

4. **Intent classifier (`chat_intent_classifier.py`)**
   - Parses the text.
   - Extracts the symbol `RELIANCE`.
   - Produces a classified intent, symbol list, and optional hints (e.g. time horizon).

5. **Market data + prediction (`stock_service` + `prediction_engine`)**
   - `stock_service` fetches current price, PE, dividend yield, sector, and history.
   - Technical indicators (RSI, MACD, moving averages) are computed.
   - `advisor_v2/prediction_engine.py` predicts expected return and confidence.

6. **Reasoning engine (`advisor_v3/reasoning_engine.py`)**
   - Combines:
     - predicted return and volatility,
     - technical indicator signals,
     - sector and market regime context,
     - basic sentiment/volume cues.
   - Outputs factor scores and a synthesized recommendation.

7. **Response generation (`advisor_v5/response_generator.py`)**
   - Formats a **“Buy Decision – RELIANCE”** answer with:
     - Valuation / fundamentals summary.
     - Momentum and technical overview.
     - AI prediction and regime context.
     - A clear conclusion and risk disclaimer.

8. **Frontend display**
   - The React UI renders the returned `message` field in the chat window.

---

## Project Directory Structure (Advisor‑Relevant)

Key directories and their roles:

- `backend/app/routes`
  - FastAPI **API endpoints** for stocks, technicals, advisor, portfolio, resilience, etc.
- `backend/app/services`
  - Core **business logic and AI modules**.
  - Advisor sub‑packages:
    - `advisor_v2` – prediction engine and signal scoring.
    - `advisor_v3` – reasoning engine and market context.
    - `advisor_v4` – quant models, regime detection, strategies, risk, optimizer.
    - `advisor_v5` – chat orchestration, intent parsing, response generation.
- `frontend`
  - **React interface** with dashboard pages, AI Advisor chat, charts, and resilience predictor UI.
- `docs`
  - **Technical documentation**, including:
    - `ARCHITECTURE.md` (this file)
    - `AI_ADVISOR.md` (advisor internals)
    - `RESILIENCE_PREDICTOR.md` (resilience model)

---

## Design Principles

The architecture is guided by a few key principles:

- **Modular architecture**
  - Each advisor generation (V2–V5) is a separate, composable layer.
  - Market data, technicals, prediction, reasoning, and response formatting are decoupled.

- **Separation of concerns**
  - Routes handle HTTP and auth concerns.
  - Services encapsulate business logic and analytics.
  - Quant/AI engines focus on models and financial logic.
  - Response generators format output for human consumption.

- **Scalable advisor layers**
  - New models and heuristics can be introduced in V2–V4 without changing the external API shape.
  - V5 can orchestrate additional sources (e.g. new models, risk engines) via intent routing.

- **Easy addition of new financial models**
  - New indicators or models can be added as separate service modules.
  - The intent classifier and reasoning engine can be extended to call them.
  - The response generator can be extended to render new metrics in textual or tabular form.

This makes FinanceMCP suitable both for **production dashboards** and as a **research playground** for new AI‑driven financial models.

