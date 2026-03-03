# BharatFinanceAI

A premium Indian fintech-style full-stack application for **Indian Markets Intelligence**. Built with FastAPI, React, Firebase Auth, and Realtime Database.

## Features

- **Authentication** – Firebase Auth (email/password) with protected routes
- **Dashboard** – Tabbed interface: Market View, Technical Analysis, AI Advisor
- **Market Overview** – Stock search, live NSE price data, add-to-watchlist
- **Technical Lab** – RSI and MACD with visual gauges (oversold/overbought)
- **AI Advisor** – Natural-language chat for stocks, SIP, mutual funds, IPOs, macro data
- **Watchlist** – Firebase-backed watchlist with live prices
- **Chat Persistence** – Messages synced to Firebase Realtime Database
- **Indian Flag Theme** – Saffron, White, Green, Navy Blue

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

| Endpoint           | Method | Description                    |
|--------------------|--------|--------------------------------|
| `/`                | GET    | Health check                   |
| `/stock/{symbol}`  | GET    | Stock quote                    |
| `/stock/search`    | GET    | Search stocks                  |
| `/stock/popular`   | GET    | Popular stocks                 |
| `/rsi/{symbol}`    | GET    | RSI for symbol                 |
| `/macd/{symbol}`   | GET    | MACD for symbol                |
| `/ask`             | POST   | Natural-language query         |
| `/ipo/upcoming`    | GET    | Upcoming IPOs                  |
| `/mutual-fund/search` | GET | Mutual fund search             |
| See `/docs`        |        | Full API documentation         |

## Environment Variables

| Variable      | Description                          |
|---------------|--------------------------------------|
| `CORS_ORIGINS`| Comma-separated frontend URLs        |

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
