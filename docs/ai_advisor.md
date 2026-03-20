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

---

## V6: Cross-Market Aware Advisor

### Overview

V6 enhances the advisor with live macro signal awareness. All responses now include a macro overlay using real-time data fetched from yfinance. Bond yields, crude oil, USD/INR, gold, and India VIX are tracked and injected into stock, portfolio, and macro responses.

### New Intent Types Added

- **Macro Signal Analysis** – Questions about bond yield, VIX, crude oil, gold, USD/INR with a standard formatted response
- **Cross-market impact** – How macro events affect Indian equities
- **Portfolio analysis with macro overlay** – Portfolio risk analysis combined with live macro risk overlay
- **Commodity comparison** – Gold, silver, oil, etc. in multi-asset comparisons

### Standard Response Formats

#### MACRO SIGNAL ANALYSIS

**Fields:** Signal, Current Value, Today Change, What This Means, Impact on Indian Markets, Current Context, Data as of

**Example:**
```text
**MACRO SIGNAL ANALYSIS**

**Signal:** India VIX
**Current Value:** 18.91
**Today Change:** -19.07% (down)

**What This Means:**
India VIX measures expected market volatility over the next 30 days. At 18.91 and falling sharply by 19%, market fear has significantly reduced today. A VIX below 20 is generally considered a calm zone.

**Impact on Indian Markets:**
Low and falling VIX is positive for equities broadly. Banking and large-cap stocks typically benefit most in low-VIX environments.

**Current Context:**
Combined with gold up 2.81%, markets are sending mixed signals. Exercise moderate caution.

**Data as of:** 10/03/2026, 05:46:26 PM IST
```

#### STOCK ANALYSIS

**Fields:** Decision, Confidence, Current Price, Fundamentals (P/E, Sector, Dividend), Technical Signals (Momentum, Prediction, Market Regime), Macro Overlay (Live), Conclusion, Risk Note

**Example:**
```text
**STOCK ANALYSIS: RELIANCE**

**Decision:** BUY
**Confidence:** 65%
**Current Price:** Rs.1,408.00

**Fundamentals:**
• P/E Ratio: 22.5 (Sector avg: ~18.0)
• Sector: Energy
• Dividend: 0.25%

**Technical Signals:**
• Momentum: 62/100
• Prediction: 58/100
• Market Regime: bullish

**Macro Overlay (Live):**
• Bond Yield 4.25 (+0.50%) — valuation pressure
• USD/INR 83.50 (+0.20%) — mixed
• India VIX 18.91 (-19.07%) — low fear

**Conclusion:**
[Combined technical + macro reasoning.]

**Risk Note:** Use this as decision support only.
```

#### PORTFOLIO ANALYSIS

**Fields:** Holdings (table with Stock, Price, Weight, Sector), Sector Breakdown, Macro Risk Overlay (Live), Risk Assessment (Diversification, Concentration, Macro Exposure), Recommendations, Risk Note

**Example:**
```text
**PORTFOLIO ANALYSIS**

**Holdings:**
| Stock    | Price    | Weight | Sector           |
|----------|----------|--------|------------------|
| RELIANCE | Rs.1408  | 40%    | Energy           |
| TCS      | Rs.2513  | 30%    | Technology       |
| HDFCBANK | Rs.849   | 30%    | Financial Svcs   |

**Sector Breakdown:**
• Energy: 40%
• Technology: 30%
• Financial Svcs: 30%

**Macro Risk Overlay (Live):**
• Crude Oil 72.50 (+1.2%): Rising oil increases input costs for energy holdings.
• Bond Yield 4.25 (+0.50%): Higher yields pressure tech holdings.
• India VIX 18.91 (-19.07%): Low VIX supports equities.

**Risk Assessment:**
• Diversification: Moderate
• Concentration: RELIANCE at 40%
• Macro Exposure: Medium risk

**Recommendations:**
[Actionable suggestions based on portfolio and live macro signals.]

**Risk Note:** Not personalised financial advice.
```

### Intent Priority Order

1. **Priority 1** – Portfolio weights detected (e.g. "Reliance 40% TCS 30%") → Portfolio Analysis with macro overlay
2. **Priority 2** – 2+ stock names + compare/vs → Comparison Table
3. **Priority 3** – Macro keywords (bond, yield, vix, gold, crude, rupee, INR) → Macro Signal Analysis
4. **Priority 4** – Single stock + buy/hold/sell → Stock Analysis with macro overlay
5. **Priority 5** – Everything else → Clarification menu fallback

### Timeout & Performance

- **Parallel signal fetching** – 6s timeout for cross-market signals
- **TTL cache** – 60s for prices, 300s for info
- **Frontend timeout** – 30s via axios default
- **Fallback responses** – If fetch fails, responses degrade gracefully without crashing

### Timestamp

All timestamps are shown in **IST (UTC+5:30)**:

`DD/MM/YYYY, HH:MM:SS AM/PM IST`

