# BharatFinanceAI

A premium Indian fintech-style full-stack application for **Indian Markets Intelligence**. Built with FastAPI, React, Firebase Auth, and Realtime Database.

In addition to the REST API, the project also ships a **Bharat Finance MCP server** (`BharatFinanceMCP_v1`) that exposes curated tools for mutual funds, IPOs, macroeconomic indicators, and Indian tax calculation to AI-native clients.

## Features

- **Authentication** – Firebase Auth (email/password) with protected routes and user-specific data (watchlists, activity).
- **Unified dashboard** – Tabbed interface for **Market View**, **Technical Analysis**, **Mutual Funds**, and **AI Advisor**.
- **Market overview (stocks)** – Search NSE symbols, view live price/volume/day range from yfinance, and add ideas to a synced equities watchlist.
- **Technical lab** – Backend-calculated RSI and MACD with visual gauges and numeric breakdowns to spot overbought/oversold and momentum shifts.
- **Mutual funds & SIP** – Search schemes via `mfapi.in`, view latest NAV and daily change, run SIP projections, and maintain a mutual fund watchlist.
- **IPO & SME tools** – Upcoming IPOs, GMP, listing performance, and SME stock analysis routes for deeper primary-market tracking.
- **Sectors & macro** – Sector performance summaries plus repo rate, inflation, and GDP routes for macro context.
- **Portfolio analytics (API)** – Endpoints to post a portfolio and get risk/return summaries and sector breakdowns (ready for future UI wiring).
- **AI advisor** – Natural-language chat for stocks, SIPs, mutual funds, IPOs, and macro concepts, embedded directly into the dashboard. See `docs/ai_advisor.md` for V1–V5 details.
- **Resilience predictor (ML + simulation)** – Financial shock resilience scoring with optional Gemini tips. See `docs/resilience_predictor.md`.
- **Watchlists** – Firebase-backed stock and mutual fund watchlists with optional local-storage mirroring for a smoother UX.
- **Chat persistence** – Messages and activity synced to Firebase Realtime Database.
- **Indian flag theme** – Saffron, white, green, and navy blue palette tailored for Indian markets.
- **MCP tools (CLI / AI clients)** – Standalone MCP server exposing mutual fund, IPO, macro, and capital-gains tools with built-in **adaptive truncation** to keep AI responses within context limits.

## Project Structure

```
bharat-finance-ai/
├── backend/
│   ├── main.py
│   ├── mcp_server.py
│   ├── requirements.txt
│   └── app/
│       ├── routes/          # stock, rsi, macd, query, IPO, MF, macro, sector, portfolio
│       ├── services/
│       ├── utils/
│       └── models/
├── src/
│   ├── server.py            # BharatFinanceMCP_v1 FastMCP server (tools over stdio)
│   ├── tools/
│   │   ├── mutual_funds.py  # NAV lookup, MF search, SIP calculator
│   │   ├── ipo.py           # Upcoming IPOs, GMP, subscription
│   │   ├── macro.py         # RBI rates, inflation (World Bank), GDP, FX reserves
│   │   └── calculators.py   # Indian capital-gains / tax estimator
│   └── utils/
│       └── optimizer.py     # Adaptive truncation for MCP tool payloads
├── frontend/
│   ├── src/
│   │   ├── components/      # Navbar, Chat, StockSearch, Watchlist, RSIGauge, MACDGauge, etc.
│   │   ├── pages/           # Landing, Dashboard, Auth
│   │   ├── context/         # AuthContext
│   │   ├── lib/             # firebase.ts
│   │   ├── services/        # api.js
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── package.json
│   └── tailwind.config.js
├── docs/
├── claude_config.json
├── render.yaml
├── render_mcp.yaml
└── README.md
```

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

## Demo

A short video walkthrough of BharatFinanceAI is available:

- **Local recording path (for reference):** `C:\\Users\\OM KUMAR SINGH\\Videos\\Captures\\BharatFinanceAI - Google Chrome 2026-03-03 12-15-27.mp4`
- After uploading this video to GitHub (e.g. in `docs/demo/` or as a release asset), update this section with a public link so others can view it directly from the README.

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
