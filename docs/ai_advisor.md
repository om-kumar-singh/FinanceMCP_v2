# AI Advisor Architecture – FinanceMCP

This document describes the **AI advisor architecture** used in the FinanceMCP platform.  
It focuses on how user queries flow through the system, the responsibilities of each layer, and how the different advisor versions (V2–V5) interact.

---

## High‑Level Goals

The AI advisor is designed to:

- Answer natural‑language questions about **stocks, portfolios, and markets**.
- Combine **machine learning**, **quantitative finance**, **technical analysis**, and **macro indicators**.
- Provide **explanations** and **risk‑aware context**, not just raw numbers.
- Expose a **clean API** for both the React frontend and AI tools (MCP / LLM agents).

At a high level, the advisor pipeline is:

> User → `/advisor/chat` → Intent parser & router → Data & models → Reasoning engine → Response generator → Text answer

---

## Advisor Layers (Conceptual)

The advisor can be understood as a stack of layers:

1. **Query routing & intent classification**
2. **Symbol & entity resolution**
3. **Market data pipeline**
4. **Technical indicator engine**
5. **Prediction & quant engines**
6. **Advisor reasoning engine**
7. **Response generator**

Each layer is implemented with concrete modules in `backend/app/services/advisor_v2` … `advisor_v5` and associated routes.

---

## 1. Query Routing & Intent Classification

**Goal**: Convert a free‑form user question into a structured intent with parameters.

Typical inputs:

- Raw query string:  
  `"Should I buy RELIANCE right now?"`  
  `"Compare TCS INFY HCLTECH and TECHM"`  
  `"What is the current market regime?"`
- Optional conversational context: last symbol, last intent, prior portfolio.

Core steps:

- **Tokenization and normalization** – lower‑casing, punctuation stripping, etc.
- **Pattern and keyword detection** – detect phrases like `compare`, `vs`, `predict`, `rebalance`, `market regime`, etc.
- **Symbol extraction** – extract stock tickers, e.g. `["TCS", "INFY", "HCLTECH", "TECHM"]`.
- **Intent scoring** – assign scores to possible intents such as:
  - `buy_decision`
  - `comparison` / `growth_comparison` / `long_term_comparison`
  - `prediction`
  - `technical_indicator`
  - `portfolio_analysis` / `portfolio_rebalance`
  - `market_regime`
  - `ai_picks` / `ai_buy_signals`
- **Final classification** – select the best intent and primary symbol (if any).

This logic lives in the **Advisor V5** layer and feeds directly into downstream engines.

---

## 2. Symbol & Entity Resolution

Once an intent is chosen, symbols and other entities must be put into a canonical form.

Responsibilities:

- Map **human‑typed names** (e.g. `"reliance"`, `"HDFC bank"`) to **exchange‑qualified tickers** such as `RELIANCE.NS`, `HDFCBANK.NS`.
- Ensure **strict symbol filtering** (for multi‑stock comparison) so only symbols explicitly mentioned in the query are included.
- Persist **last used symbol(s)** in chat context to support follow‑ups like
  - `"What about its RSI now?"`
  - `"Compare it to TCS instead."`

Outputs of this layer are used by:

- Market data fetchers.
- Technical indicator and prediction engines.
- Comparison and portfolio modules.

---

## 3. Market Data Pipeline

**Goal**: Provide a unified, cached view of market data to all advisor layers.

Key sources:

- Stock quotes and OHLCV history via **yfinance**.
- Sector and index summaries (e.g. NIFTY, sector indices).
- Mutual fund data via external APIs (for some portfolio features).
- Market news for news‑based sentiment and macro stress heuristics.

Responsibilities:

- Fetch and normalize:
  - latest price, day high/low, 52‑week ranges
  - PE ratio, dividend yield, market cap, sector.
- Provide consistent dataframes / dicts that higher layers can consume.
- Handle timeouts and errors gracefully so the advisor never crashes the chat.

Most of this lives in `backend/app/services/stock_service.py`, `sector_service.py`, and `news_service.py`, which are reused across advisor versions.

---

## 4. Technical Indicator Engine

**Goal**: Turn historical price/volume data into technical indicators for trading‑style analysis.

Indicators computed include:

- **RSI (Relative Strength Index)**
- **MACD (Moving Average Convergence Divergence)** + signal line + histogram
- **Moving averages**:
  - SMA20 (short‑term trend)
  - SMA50 (intermediate trend)
  - SMA200 (long‑term trend)
- Derived **momentum and overbought/oversold flags**.

These indicators are used for:

- Dedicated API endpoints (e.g. RSI/MACD charts in the dashboard).
- Advisor V2/V3/V4 models as features for prediction and scoring.
- V5 chat responses for “What does RSI/MACD say about X?” style questions.

---

## 5. Prediction & Quant Engines

The platform ships multiple “advisor generations” that build on top of each other.

### Advisor V2 – Prediction Engine & Signal Scoring

**Purpose**:

- Ensemble‑style **price prediction** for single stocks.
- Score signals based on technicals, returns, and risk.
- Provide structured analytics for future dashboards.

Key components:

- **Prediction engine** – runs ensemble forecasts over short/medium horizons, returning:
  - expected return
  - predicted price
  - confidence metrics.
- **Signal scoring** – aggregates technical and model signals into normalized factor scores.
- **Portfolio risk** – simple volatility, diversification, and concentration measures.

### Advisor V3 – Reasoning Engine

**Purpose**:

- Combine V2 predictions with:
  - market regime context
  - sector performance
  - news‑based sentiment
  - simple volume and volatility adjustments.
- Produce **multi‑factor stock scores** and explanation dictionaries.

Outputs:

- Per‑stock:
  - recommendation (BUY / HOLD / SELL‑like)
  - expected return
  - factor scores: prediction, momentum, sentiment, trend, volatility, etc.
  - explanation text for the response generator.

### Advisor V4 – Quant Engine

**Purpose**:

- Add more “hedge‑fund style” tools:
  - **market regime detection** – bull / bear / sideways + volatility level.
  - **strategy ensembles** – momentum, mean‑reversion, volatility breakout, etc.
  - **smart‑money detection** – unusual volume and price action patterns.
  - **portfolio optimizer** – Markowitz‑style allocation suggestions.
  - **risk metrics** – VaR / expected shortfall approximations and drawdown stats.

V4 outputs are folded into V5’s reasoning for market outlook, risk commentary, and portfolio suggestions.

---

## 6. Advisor Reasoning Engine (V5)

Advisor V5 acts as the **orchestrator** that glues everything together for conversational use.

Responsibilities:

- Take the **intent classification** results and decide which engines to call:
  - V2 prediction
  - V3 reasoning
  - V4 quant / regime
  - portfolio analytics
  - comparison or screener modules.
- Merge outputs into a unified reasoning object, e.g.:
  - prediction & confidence
  - factor scores
  - regime context
  - risk metrics
  - portfolio hints.
- Apply **guardrails**:
  - never provide guaranteed advice
  - clearly tag speculative results
  - encourage diversification and risk management.

For multi‑stock queries (e.g. comparisons), this engine also:

- Fetches metrics for each symbol (price, PE, dividend yield, sector, market cap).
+- Ranks stocks on valuation, income, size, and (optionally) growth‑style scores.

---

## 7. Response Generator

Once reasoning is complete, the **response generator** turns structured data into readable text.

Key responsibilities:

- Format **single‑stock analyses** with sections such as:
  - “Advisor Recommendation – SYMBOL”
  - “Score breakdown”
  - “Interpretation” and “Risk factors”.
- Render **multi‑stock comparison tables**, for example:

```text
Stock Comparison

Stock           Price      P/E   Dividend     Sector
----------------------------------------------------
INFY         ₹1,308.40    18.5      3.44%  Technology
TCS          ₹2,557.60    19.4      2.46%  Technology
HCLTECH      ₹1,356.70    22.4      3.98%  Technology
TECHM        ₹1,331.70    25.5      3.38%  Technology

Interpretation
• INFY has the lowest valuation based on P/E among the compared stocks.
• HCLTECH offers the highest dividend yield in this group.
• TCS is the largest company by reported market capitalisation.

Conclusion
Valuation leader → INFY
Income leader   → HCLTECH
Size leader     → TCS
```

- Guarantee that **chat never returns raw JSON** – all dictionaries are converted into readable text before leaving the backend.
- Simplify the shape for the frontend: the UI mainly needs a `message` string plus a few metadata fields such as `source` and `query`.

---

## Example Request Flow

This is a typical flow for a query like:

> “Compare TCS INFY HCLTECH and TECHM for long‑term investment”

1. **Frontend**
   - React chat component sends `POST /advisor/chat` with the text query and optional context (e.g. last symbols).

2. **Query Router & Intent Parser (V5)**
   - Classifies the intent as `comparison` or `long_term_comparison`.
   - Extracts explicit symbols: `["TCS", "INFY", "HCLTECH", "TECHM"]`.

3. **Symbol Resolution**
   - Resolves to canonical tickers, e.g. `TCS.NS`, `INFY.NS`, `HCLTECH.NS`, `TECHM.NS`.

4. **Data & Indicator Layer**
   - Fetches quotes and fundamentals (price, PE, dividend yield, sector, market cap) for each symbol.
   - Optionally computes momentum/technical scores and growth‑style metrics.

5. **Comparison / Quant Logic**
   - Builds a list of per‑stock rows.
   - Determines leaders:
     - lowest P/E → valuation leader
     - highest dividend yield → income leader
     - largest market cap → size leader
     - highest growth score (if prediction data is present) → growth candidate.

6. **Reasoning & Explanation**
   - Generates interpretation bullets (e.g. “INFY appears cheapest based on P/E.”).
   - Generates conclusion lines summarizing leaders and caveats.

7. **Response Generation**
   - Converts the rows + leaders + interpretation + conclusion into a text table plus bullet list.
   - Returns a payload whose `message` field is ready to render in chat.

8. **Frontend Rendering**
   - Displays the formatted text response in the chat UI.
   - Optionally logs the underlying `source` and intent for analytics.

---

## Example Request Flow – Single‑Stock “Should I buy?”

For a question like:

> “Should I buy RELIANCE right now? Explain your reasoning.”

1. **Intent**: `buy_decision` with primary symbol `RELIANCE.NS`.
2. **Data**: fetch latest quote + fundamentals; compute RSI/MACD and moving averages.
3. **Prediction**: run the ensemble model to get expected return and confidence.
4. **Reasoning**:
   - combine prediction, momentum, sentiment, trend, and volatility into factor scores;
   - bring in current market regime (bull / bear / sideways).
5. **Response generation**:
   - produce a “Buy Decision – RELIANCE” section with:
     - Valuation / Fundamentals
     - Momentum
     - AI Prediction
     - Market Regime
     - Conclusion with a BUY / HOLD / AVOID‑style tag and risk warnings.

---

## Summary

- The AI advisor is a **layered architecture** that separates:
  - intent parsing,
  - data fetching,
  - technical and quant model computation,
  - reasoning,
  - and final response formatting.
- It supports both **single‑stock** and **multi‑stock** workflows, plus **portfolio** and **market‑level** questions.
- The design is intentionally **modular**, so models and heuristics can evolve without breaking the external API or chat experience.

