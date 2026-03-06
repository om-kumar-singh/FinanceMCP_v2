# FinanceMCP – AI Financial Intelligence Platform

FinanceMCP is an end‑to‑end **AI financial intelligence platform** that combines:

- **AI stock advisor**
- **financial resilience predictor**
- **portfolio analysis and optimization**
- **market regime detection**
- **AI‑driven stock forecasting**

The system merges ideas from **machine learning**, **quantitative finance**, **technical analysis**, and **macro indicators** into a unified AI assistant for Indian markets.

The same backend powers:

- A React dashboard for human users.
- Programmatic APIs for developers and quants.
- An AI‑native MCP server that exposes tools to language models.

---

## Core Features

### AI Stock Advisor

Conversational AI that answers real‑world investment questions such as:

- **“Should I buy this stock?”**
- **“Give me a fundamentals view on TCS.”**
- **“What do RSI and MACD say about INFY?”**
- **“What’s the AI‑predicted return for RELIANCE?”**
- **“What is the current market regime?”**
- **“How should I rebalance my portfolio?”**

Under the hood, the advisor:

- Parses natural‑language queries into structured intents.
- Fetches live market data and technical indicators.
- Runs ensemble prediction models and quant screens.
- Generates human‑readable, risk‑aware explanations.

See `docs/AI_ADVISOR.md` for a deep dive into the advisor architecture.

---

### Financial Resilience Predictor

The **financial resilience predictor** estimates how well a person can handle financial shocks (job loss, market crashes, emergencies).

- **Inputs** typically include:
  - income
  - savings and liquid assets
  - recurring expenses
  - debt and EMIs
  - employment stability / sector risk
- **Output**:
  - a **financial resilience score** (0–100)
  - qualitative risk band (e.g. strong / moderate / vulnerable)
  - runway in months and scenario‑specific adjustments

This module uses ML models, Monte Carlo simulation, and macro stress signals to summarize a household’s shock‑absorbing capacity.

See `docs/RESILIENCE_PREDICTOR.md` for full details.

---

### AI Prediction Engine

The prediction engine forecasts **short‑term stock movements** using an ensemble of models:

- Uses:
  - price momentum signals
  - technical indicators (RSI, MACD, moving averages)
  - volatility modeling and regime adjustments
- Outputs:
  - **expected return** (as a fraction or %)
  - **predicted price** for a selected horizon
  - **confidence score/label**

These predictions are surfaced via:

- Advisor endpoints (`/advisor/v2`, `/advisor/v3`, `/advisor/v4`).
- The conversational AI advisor (Advisor V5) for “What does AI predict for X?” queries.

---

### Portfolio Intelligence

Portfolio analytics modules provide:

- **Risk analysis** – volatility, drawdown, concentration, beta‑like metrics.
- **Diversification scoring** – sector/stock concentration and Herfindahl‑style indices.
- **Allocation analysis** – sector and asset‑class level splits.
- **Optimization** – Markowitz‑style approximations to suggest more balanced allocations.

These capabilities feed into both:

- REST APIs for portfolio dashboards.
- The AI advisor’s **“analyze my portfolio”** and **“how should I rebalance?”** intents.

---

### Market Regime Detection

Market regime engines classify the current state of the index (e.g. NIFTY) as:

- **bullish**
- **bearish**
- **sideways / range‑bound**

using:

- trend strength
- volatility levels
- recent index returns

The regime is used to:

- Provide standalone market context (“What is the market regime?”).
- Adjust portfolio and position‑sizing suggestions inside the AI advisor.

---

## Tech Stack

### Frontend

- **React + Vite** – modern SPA architecture.
- TailwindCSS and custom components for charts, watchlists, and the chat UI.

### Backend

- **FastAPI** – high‑performance Python API server.
- Layered services in `backend/app/services` for data, analytics, and AI.

### ML / Quant

- **Python** (NumPy, pandas, scikit‑learn, etc.).
- Custom models and heuristics for:
  - ensemble price prediction
  - volatility modeling
  - portfolio risk scoring
  - financial resilience estimation.

### Market Data

- **yfinance** – quotes, historical OHLCV, and basic fundamentals.
- Additional HTTP APIs for mutual funds, macro data, and news when configured.

### Visualization

- Charting libraries on the frontend (e.g. candlesticks, line charts, gauges).
- Textual summaries and tabular views in the AI advisor responses.

---

## System Architecture

The AI advisor stack is organized into **layers**, each with a focused responsibility.

### Layer 1 – Query Router & Intent Parser

- Parses the user’s natural‑language query.
- Extracts:
  - primary intent (e.g. prediction, comparison, portfolio analysis)
  - entities (stock symbols, sectors, time horizons)
  - additional constraints (risk appetite, long‑term vs short‑term, etc.).
- Routes to one or more downstream engines:
  - prediction
  - technicals
  - quant models
  - portfolio analytics
  - resilience predictor.

### Layer 2 – Market Data Engine

- Fetches:
  - current prices
  - OHLCV history
  - sector and index data
  - news headlines.
- Normalizes data into a consistent internal structure reused across advisor versions.

### Layer 3 – Technical Indicator Engine

- Computes:
  - RSI
  - MACD and signal line
  - simple / exponential moving averages (SMA20, SMA50, SMA200, etc.)
  - momentum and overbought/oversold flags.
- Exposes outputs to both REST APIs and higher‑level advisor modules.

### Layer 4 – Prediction Engine

- Ensemble models ingest:
  - recent price history
  - volatility estimates
  - technical indicators and simple features.
- Produces:
  - expected return
  - predicted price for each horizon
  - confidence score / label.

### Layer 5 – Advisor Reasoning Engine

- Combines signals from:
  - prediction engine
  - technical indicators
  - market regime detector
  - news sentiment
  - portfolio risk modules.
- Produces:
  - multi‑factor stock scores
  - explanations and rationales
  - recommendations tagged with risk and confidence.

### Layer 6 – Response Generator

- Converts structured analysis into **human‑readable** responses:
  - formatted text
  - sections (Summary, Interpretation, Risk, Conclusion)
  - comparison tables for multi‑stock queries.
- Guarantees that chat responses are **never raw JSON**, making them suitable for both humans and AI tools.

---

## Project Structure

High‑level layout:

```text
bharat-finance-ai/
├── backend/
│   ├── main.py
│   ├── mcp_server.py
│   └── app/
│       ├── routes/          # API endpoints (stocks, technicals, portfolio, advisor, resilience, etc.)
│       ├── services/        # Core business and analytics logic
│       ├── utils/
│       └── models/
├── src/
│   ├── server.py            # Finance MCP server (tools over stdio)
│   ├── tools/               # Mutual funds, IPO, macro, tax tools
│   └── utils/               # MCP payload optimizer
├── frontend/
│   ├── src/
│   │   ├── components/      # Chat, charts, watchlists, dashboards
│   │   ├── pages/           # Dashboard, Resilience Predictor, etc.
│   │   ├── context/
│   │   ├── lib/
│   │   └── services/
│   └── package.json
├── docs/                    # Technical documentation (AI advisor, resilience predictor, MCP, ...)
└── README.md
```

### Key advisor/quant modules

- `backend/app/routes`
  - API endpoints for stocks, technical indicators, portfolio, advisor, and resilience.
- `backend/app/services`
  - **advisor_v2** – prediction engine and signal scoring.
  - **advisor_v3** – reasoning engine.
  - **advisor_v4** – quant engine (regime detection, strategies, risk).
  - **advisor_v5** – chat interface, intent parsing, and response generation.
- `frontend`
  - React UI, including the AI Advisor chat and Resilience Predictor screens.
- `docs`
  - `AI_ADVISOR.md` – detailed advisor architecture.
  - `RESILIENCE_PREDICTOR.md` – resilience prediction system.

---

## External APIs and Data Sources

The platform is designed to reuse existing, battle‑tested data sources:

- **yfinance**
  - Stock quotes, OHLCV history.
  - Basic fundamentals (PE, dividend yield, sector, market cap).
  - Index and sector data.
- **Mutual fund APIs** (e.g. `mfapi.in`)
  - NAV history and scheme metadata for Indian mutual funds.
- **Macro indicators**
  - GDP growth (e.g. World Bank).
  - Inflation / CPI series.
  - RBI repo rate and other policy rates.
- **Market news APIs** (optional)
  - For simple sentiment and macro stress heuristics.

The specific configuration of keys and endpoints is environment‑driven; see environment configuration files for details.

---

## Algorithms and Indicators

Key financial and ML/quant building blocks used in the system include:

- **RSI (Relative Strength Index)**
- **MACD (Moving Average Convergence Divergence) and signal line**
- **Moving averages**
  - SMA20
  - SMA50
  - SMA200
- **Momentum indicators**
- **Ensemble prediction models**
- **Volatility estimation**
  - standard deviation of log returns
  - regime‑aware heuristics.
- **Portfolio risk scoring**
  - diversification and concentration measures
  - simple VaR/ES‑style metrics in quant modules.

---

## Mathematical Formulas (Core)

### Relative Strength Index (RSI)

\[
RSI = 100 - \left( \frac{100}{1 + RS} \right)
\]

where:

\[
RS = \frac{\text{average gain}}{\text{average loss}}
\]

over a chosen look‑back period (commonly 14 days).

---

### MACD (Moving Average Convergence Divergence)

\[
MACD = EMA_{12} - EMA_{26}
\]

with:

- \( EMA_{12} \): 12‑period exponential moving average.
- \( EMA_{26} \): 26‑period exponential moving average.

Signal line:

\[
\text{Signal} = EMA_9(MACD)
\]

Histogram:

\[
\text{Histogram} = MACD - \text{Signal}
\]

---

### Expected Return

For a single forecast horizon:

\[
\text{Expected Return} = \frac{\text{Predicted Price} - \text{Current Price}}{\text{Current Price}}
\]

This is typically expressed as a percentage in the advisor responses.

---

### Volatility

Volatility is approximated as the **standard deviation of log returns**:

\[
r_t = \ln\left(\frac{P_t}{P_{t-1}}\right)
\]
\[
\sigma = \sqrt{\frac{1}{N-1}\sum_{t=1}^{N} (r_t - \bar{r})^2}
\]

where:

- \( P_t \) is the price at time \( t \).
- \( r_t \) is the log return.
- \( \sigma \) is the volatility estimate.

---

### Z‑score (Volume analysis)

Used in unusual‑volume / smart‑money style scans:

\[
Z = \frac{\text{Current Volume} - \text{Mean Volume}}{\text{Standard Deviation of Volume}}
\]

Higher positive \( Z \) suggests unusually high volume; low or negative values suggest normal or weak participation.

---

## What Makes This Project Unique

Compared with tools like **Yahoo Finance**, **TradingView**, or generic **ChatGPT financial plug‑ins**, this project is designed as a **modular AI financial platform**:

- **AI conversational advisor**
  - Domain‑aware intent parsing and symbol resolution.
  - Multi‑layer reasoning with predictions, technicals, and regime context.
- **Quant‑based predictions**
  - Ensemble forecasts instead of single black‑box outputs.
  - Rich factor breakdowns for transparency.
- **Portfolio intelligence**
  - Risk and diversification analytics.
  - Example optimizations and rebalancing hints.
- **Market regime detection**
  - Explicit bull/bear/sideways classification.
  - Integration into position sizing and risk commentary.
- **ML resilience prediction**
  - Household‑level financial resilience, not just asset‑level risk.
- **Modular AI architecture**
  - Advisor V2–V5 are composable, making it easy to extend or swap models without breaking the frontend.

The result is a stack that is suitable both for **end‑users** (via the dashboard) and **AI agents** (via MCP tools and structured APIs).

---

## Future Improvements

Some directions for extending FinanceMCP:

- **Real‑time market data feeds**
  - WebSocket quotes and order‑book snapshots.
  - Intraday regime and microstructure‑aware indicators.
- **Deep learning models**
  - LSTM / Transformer models for sequence prediction.
  - Hybrid models combining fundamentals and price action.
- **Enhanced institutional flow detection**
  - More granular volume‑profile analysis.
  - Cross‑asset and derivatives‑driven flow heuristics.
- **Risk‑adjusted portfolio optimization**
  - Sharpe, Sortino, and drawdown‑aware optimizers.
  - Multi‑objective optimization (return, risk, diversification).
- **Richer explanation layers**
  - Counterfactual “what‑if” analysis for portfolios.
  - Scenario‑based narratives (e.g. rate‑hike shocks, sector rotations).

---

## Getting Started (Quick)

1. **Backend**
   - `cd backend`
   - `python -m venv venv && venv\Scripts\activate` (Windows) or `source venv/bin/activate` (Unix)
   - `pip install -r requirements.txt`
   - `uvicorn main:app --host 127.0.0.1 --port 8000`
2. **Frontend**
   - `cd frontend`
   - `npm install`
   - `npm run dev`
3. Open the app in your browser and explore:
   - AI Advisor chat.
   - Technical analysis tools.
   - Portfolio and resilience modules.

For deeper internals, start with:

- `docs/AI_ADVISOR.md`
- `docs/RESILIENCE_PREDICTOR.md`

## Setup

### Prerequisites

- Python 3.9+
- Node.js 18+
- Firebase project (Auth + Realtime Database)

### Backend

1. Navigate to the backend directory:

   ```bash
   cd backend
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # macOS/Linux:
   source venv/bin/activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Start the server:

   ```bash
   uvicorn main:app --host 127.0.0.1 --port 8000
   ```

   - API: `http://127.0.0.1:8000`
   - Swagger: `http://127.0.0.1:8000/docs`

### Frontend

1. Navigate to the frontend directory:

   ```bash
   cd frontend
   ```

2. Install dependencies:

   ```bash
   npm install
   ```

3. Start the dev server:

   ```bash
   npm run dev
   ```

   - App: `http://localhost:5173` (or next available port)
   - Ensure the backend is running at `http://localhost:8000`

### Firebase

Configure Firebase in `frontend/src/lib/firebase.ts` with your project config. Ensure:

- **Authentication** – Email/Password sign-in method enabled
- **Realtime Database** – Rules allow read/write for authenticated users, e.g.:

  ```json
  {
    "rules": {
      "users": {
        "$uid": {
          ".read": "$uid === auth.uid",
          ".write": "$uid === auth.uid"
        }
      }
    }
  }
  ```

## API Overview

High‑level view of key backend routes (see `/docs` for the full OpenAPI schema):

| Endpoint                         | Method | Description                                        |
|----------------------------------|--------|----------------------------------------------------|
| `/`                              | GET    | Health check                                       |
| `/stock/{symbol}`                | GET    | Stock quote for NSE/BSE symbol                     |
| `/stock/search`                  | GET    | Search stocks by name or symbol                    |
| `/stock/popular`                 | GET    | Curated list of popular NSE stocks                 |
| `/rsi/{symbol}`                  | GET    | RSI for a symbol                                   |
| `/macd/{symbol}`                 | GET    | MACD for a symbol                                  |
| `/news/{symbol}`                 | GET    | Market news for a stock/index via yfinance         |
| `/mutual-fund/{scheme_code}`     | GET    | Latest NAV for a mutual fund scheme                |
| `/mutual-fund/search`            | GET    | Mutual fund search by name/keyword                 |
| `/sip`                           | GET    | SIP future value calculator                        |
| `/capital-gains`                 | GET    | Capital gains/tax calculator (equity/debt)         |
| `/ipos`                          | GET    | Upcoming IPOs                                      |
| `/gmp`                           | GET    | Grey Market Premium data                           |
| `/ipo-performance`               | GET    | Recent IPO listing performance                     |
| `/sme/{symbol}`                  | GET    | SME stock analysis                                 |
| `/sector/{sector_name}`          | GET    | Detailed performance for a sector                  |
| `/sectors/summary`               | GET    | Performance summary across sectors                 |
| `/sectors/list`                  | GET    | List of supported sector names                     |
| `/repo-rate`                     | GET    | Latest RBI repo rate                               |
| `/inflation`                     | GET    | India CPI inflation time‑series                    |
| `/gdp`                           | GET    | India GDP growth time‑series                       |
| `/portfolio/analyze`             | POST   | Portfolio risk/return and sector analytics         |
| `/portfolio/summary`             | POST   | Lightweight portfolio summary                       |
| `/predict-resilience`            | POST   | Financial shock resilience scoring (ML + simulation) |
| `/advisor/v2/stock`              | POST   | Advisor V2: stock analytics (optional)             |
| `/advisor/v2/portfolio`          | POST   | Advisor V2: portfolio analytics (optional)         |
| `/advisor/v3/analyze`            | POST   | Advisor V3: reasoning + factor scoring (optional)  |
| `/advisor/v4/quant-analysis`     | POST   | Advisor V4: quant strategies + VaR/ES (optional)   |
| `/advisor/chat`                  | POST   | Advisor V5: conversational assistant (optional)    |
| `/advisor/insights`              | GET    | Advisor V5: AI insights feed (optional)            |

## Documentation

- **AI Advisor (V1–V5)**: `docs/ai_advisor.md`
- **Resilience Predictor**: `docs/resilience_predictor.md`
- **MCP setup**: `docs/mcp_setup.md`

## MCP Tools Overview

The **BharatFinanceMCP_v1** server (in `src/server.py`) exposes a set of AI-first tools over MCP/stdio. Highlights:

- **Mutual funds (`src/tools/mutual_funds.py`)**
  - `get_mutual_fund_nav_tool` – Latest NAV and daily change for a scheme.
  - `mutual_fund_search_tool` – Search schemes via `mfapi.in`.
  - `sip_calculator_tool` – SIP projection using standard compounding.
- **IPO & SME (`src/tools/ipo.py`)**
  - `get_upcoming_ipos_tool` – Mainboard + SME IPO pipeline with key terms.
  - `get_ipo_gmp_tool` – Grey Market Premium (GMP) with fuzzy name matching.
  - `get_ipo_subscription_tool` – Live subscription (QIB / NII / Retail).
- **Macroeconomy (`src/tools/macro.py`)**
  - `get_rbi_rates_tool` – RBI policy rates + CRR (scraped with fallbacks).
  - `get_india_inflation_tool` – Latest CPI from World Bank, WPI note.
  - `get_india_gdp_growth_tool` – Latest annual GDP growth (World Bank).
  - `get_forex_reserves_tool` – FX reserves (USD mn) from RBI WSS.
- **Tax calculators (`src/tools/calculators.py`)**
  - `calculate_indian_tax_tool` – Indian capital-gains estimate for equity, equity MF, debt MF, and gold, with INR output formatted in lakhs/crores.

All MCP tools are wrapped with **`optimize_payload`** from `src/utils/optimizer.py` to:

- Trim historical price arrays to the last 5 entries.
- Truncate long descriptions / news summaries to ~200 characters.
- Drop non-essential metadata (like `uuid`, `internal_id`).

This **adaptive truncation** helps prevent “overloaded context” errors in AI clients while preserving the essential financial insight.

## Environment Variables

All API keys and secrets must be set via environment variables. Copy `.env.example` to `.env` in each directory and fill in values. **Never commit `.env` files** — they are in `.gitignore`.

### Backend

Copy `backend/.env.example` to `backend/.env`:

| Variable              | Description                                  |
|-----------------------|----------------------------------------------|
| `CORS_ORIGINS`        | Comma-separated list of frontend URLs        |
| `MF_API_BASE_URL`     | Mutual fund API base (optional, has default) |
| `NSE_CSV_URL`         | NSE equities list URL (optional)             |
| `INFLATION_API_URL`   | World Bank inflation API (optional)          |
| `GDP_API_URL`         | World Bank GDP API (optional)                |
| `IPO_LIST_URL`        | IPO list source URL (optional)               |
| `IPO_PERFORMANCE_URL` | IPO performance source (optional)            |
| `GMP_URL`             | GMP data source URL (optional)               |

### Frontend (Vite)

Copy `frontend/.env.example` to `frontend/.env`:

| Variable                        | Description                                      |
|---------------------------------|--------------------------------------------------|
| `VITE_API_URL`                  | Backend API base URL                             |
| `VITE_FIREBASE_API_KEY`         | Firebase API key (required)                      |
| `VITE_FIREBASE_AUTH_DOMAIN`     | Firebase auth domain                             |
| `VITE_FIREBASE_PROJECT_ID`      | Firebase project ID                              |
| `VITE_FIREBASE_STORAGE_BUCKET`  | Firebase storage bucket                          |
| `VITE_FIREBASE_MESSAGING_SENDER_ID` | Firebase messaging sender ID                 |
| `VITE_FIREBASE_APP_ID`          | Firebase app ID                                  |
| `VITE_FIREBASE_MEASUREMENT_ID`  | Firebase analytics measurement ID (optional)     |
| `VITE_NEWSAPI_KEY`              | NewsAPI key for news fallback (optional)         |
| `VITE_FINNHUB_KEY`              | Finnhub key for news fallback (optional)         |
| `VITE_CORS_PROXY`               | CORS proxy URL (optional)                        |
| `VITE_MFAPI_BASE_URL`           | Mutual fund search API base (optional)           |

## Deploy to Render

The backend is configured for [Render](https://render.com).

### Blueprint

1. Push this repo to GitHub.
2. In [Render Dashboard](https://dashboard.render.com), create a **Blueprint**.
3. Connect the repo; Render will use `render.yaml`.
4. Add `CORS_ORIGINS` with your frontend URL(s).

### Manual Web Service

1. Create a **Web Service** on Render.
2. Configure:
   - **Root Directory:** `backend`
   - **Build:** `pip install -r requirements.txt`
   - **Start:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
3. Add `CORS_ORIGINS` (comma-separated URLs).

After deployment, set the frontend `baseURL` in `api.js` to your Render API URL.

## License

MIT
