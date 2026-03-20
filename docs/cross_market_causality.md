# Cross-Market Causality Detection Engine

## Overview

The Cross-Market Causality Detection Engine connects macroeconomic signals to sector movements and stock predictions. It is the intelligence layer between the Market Data Engine and the Prediction Engine.

## Architecture

```
Market Data Engine
        ↓
Cross-Market Causality Engine
        ↓
Prediction Engine
        ↓
Advisor Reasoning Engine
```

## Components

### 1. Data Fetcher

**File:** `backend/app/services/cross_market_service.py`

- Fetches 5 live macro signals via yfinance
- Parallel fetch using ThreadPoolExecutor
- 6 second global timeout
- Cached via TTLCache (60s TTL)

**Signals tracked:**

| Signal         | Ticker      | Cache TTL |
|----------------|-------------|-----------|
| US 10Y Yield   | ^TNX        | 60s       |
| Crude Oil WTI  | CL=F        | 60s       |
| USD/INR        | USDINR=X    | 60s       |
| Gold           | GC=F        | 60s       |
| India VIX      | ^INDIAVIX   | 60s       |

### 2. Causality Engine

**File:** `backend/app/services/causality_engine.py`

- Rule-based causal inference (no ML)
- 5 causal rules with configurable thresholds

**Rules:**

| Signal      | Threshold  | Impact                              | Severity        |
|-------------|------------|-------------------------------------|-----------------|
| Bond Yield  | >0.5% up   | IT/Tech valuation pressure          | high if >1%     |
| Crude Oil   | >1.0% up   | Aviation/Logistics cost pressure    | medium          |
| USD/INR     | >0.3% up   | IT/Pharma export benefit            | low             |
| India VIX   | >5.0% up   | Broad market fear                   | high            |
| Gold        | >0.5% up   | Risk-off, defensive preferred       | low             |

### 3. API Endpoints

**File:** `backend/app/routes/cross_market.py`

| Endpoint                 | Method | Description                |
|--------------------------|--------|----------------------------|
| /cross-market/signals    | GET    | Live macro signals only    |
| /cross-market/analysis   | GET    | Signals + causal insights  |

**Response format for /cross-market/analysis:**

```json
{
  "signals": {
    "bond_yield":  { "current_value", "previous_value", "change_pct", "direction" },
    "crude_oil":   { "current_value", "previous_value", "change_pct", "direction" },
    "usd_inr":     { "current_value", "previous_value", "change_pct", "direction" },
    "gold":        { "current_value", "previous_value", "change_pct", "direction" },
    "india_vix":   { "current_value", "previous_value", "change_pct", "direction" }
  },
  "causal_insights": [
    {
      "signal_name":       "string",
      "current_value":     "float",
      "change_pct":        "float",
      "impact":            "string",
      "affected_sectors":  ["list"],
      "severity":          "low | medium | high"
    }
  ],
  "insight_count":    "integer",
  "data_timestamp":   "DD/MM/YYYY, HH:MM:SS AM/PM IST"
}
```

### 4. Frontend Panel

**File:** `frontend/src/components/CrossMarketPanel.jsx`

**Features:**

- Live Macro Signals section (5 signal cards)
- Causal Insights section
- Click-to-expand ⓘ info boxes per signal
- Auto-refresh every 60 seconds
- Color-coded severity badges
- IST timestamp display

**Signal card colors:**

| Signal       | Border Color |
|--------------|--------------|
| Bond Yield   | Blue         |
| Crude Oil    | Orange       |
| USD/INR      | Green        |
| Gold         | Amber        |
| India VIX    | Red          |

### 5. AI Advisor Integration

**File:** `backend/app/services/chat_advisor_service.py` (chat handler)

- Live signals injected into macro/stock/portfolio responses
- Macro-aware responses for all question types
- IST timestamps on all data snapshots
- Timeout: 5s for signal fetch, 25s for AI model

## Causal Chain Examples

### Example 1: Rising Bond Yields

US 10Y Yield ↑ above threshold  
→ Global liquidity tightens  
→ Growth stock discount rates rise  
→ IT sector valuations drop  
→ INFY, TCS predicted returns revised down  

### Example 2: Crude Oil Spike

WTI Crude ↑ above threshold  
→ Input costs rise for oil-dependent sectors  
→ Aviation, Logistics, Paints face margin pressure  
→ Inflation risk increases  
→ RBI may tighten policy  

### Example 3: INR Weakening

USD/INR ↑ above threshold  
→ Indian exports become cheaper globally  
→ IT and Pharma exporters benefit  
→ Oil import bill increases  
→ Trade deficit widens  

### Example 4: Gold Rally

Gold ↑ above threshold  
→ Risk-off sentiment detected  
→ Investors moving to safe havens  
→ Defensive sectors preferred (Banking, FMCG)  
→ Broad equity caution advised  

### Example 5: VIX Spike

India VIX ↑ above threshold  
→ Market fear and uncertainty rising  
→ All sectors face short-term selling pressure  
→ Position sizing and stop-loss critical  

## Known Limitations

### 1. Correlation vs Causation

Rules detect correlation patterns, not true causal relationships. A signal crossing a threshold does not guarantee the stated market impact.

### 2. Regime Changes

Causal relationships change across economic cycles. Example: Oil up was bullish in 2010, bearish in 2022. Current rules are static and do not adapt to regime.

### 3. Hidden Variables

Policy decisions, geopolitical events, and regulatory changes are not captured by the 5 signal model.

## Future Improvements

- Add Granger causality statistical testing
- Add regime-aware rule switching
- Add more signals: FII flows, credit spreads, PMI
- Add ML-based dynamic threshold adjustment
- Add sector ETF correlation tracking

## Setup & Configuration

No additional configuration required beyond the existing backend setup. The engine uses the same yfinance dependency already in `requirements.txt`.

- **Environment variables:** None required.
- **Signal sources:** All public (yfinance).
