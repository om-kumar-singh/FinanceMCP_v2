# BharatFinanceMCP - Claude Desktop Setup Guide

## Step 1: Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

## Step 2: Test MCP Server directly

```bash
cd backend
python mcp_server.py
```

If no errors appear, the server is ready.

## Step 3: Find Claude Desktop Config Location

- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **Mac:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux:** `~/.config/Claude/claude_desktop_config.json`

## Step 4: Add MCP Server to Claude Desktop Config

1. Open `claude_config.json` in the project root.
2. Replace `FULL_PATH_TO` with the absolute path to your project directory.
   - Windows example: `C:/Users/YourName/projects/BharatFinanceMCP`
   - Mac/Linux example: `/home/yourname/projects/BharatFinanceMCP`
3. Copy the `mcpServers` section into `claude_desktop_config.json`.

Example merged section:

```json
{
  "mcpServers": {
    "BharatFinanceMCP": {
      "command": "python",
      "args": ["C:/Users/YourName/projects/BharatFinanceMCP/backend/mcp_server.py"],
      "env": {
        "PYTHONPATH": "C:/Users/YourName/projects/BharatFinanceMCP/backend"
      }
    }
  }
}
```

## Step 5: Restart Claude Desktop

Fully quit and reopen Claude Desktop.

Look for the hammer icon (🔨) in the chat interface.
Click it to see available BharatFinanceMCP tools.

## Step 6: Test with these queries in Claude Desktop

- "What is the current price of Reliance Industries?"
- "Calculate RSI for TCS for 14 days"
- "Show me top 5 gainers on NSE today"
- "What is the NAV of HDFC Top 100 fund? scheme code 119551"
- "Calculate SIP of ₹5000 for 10 years at 12% returns"
- "Show upcoming IPOs"
- "What is the current repo rate?"
- "Show me IT sector performance"
- "Analyze my portfolio: 10 shares of Reliance at ₹2000, 5 shares of TCS at ₹3500"

## Cross-Market Tools Added in V2

New tools added to BharatFinanceMCP_v1:

### get_cross_market_signals

- Returns live data for 5 macro signals
- Tickers: ^TNX, CL=F, USDINR=X, GC=F, ^INDIAVIX
- Fields: `current_value`, `previous_value`, `change_pct`, `direction`
- Cached: 60s TTL

### get_cross_market_analysis

- Returns signals + causal insights combined
- Includes `data_timestamp` in IST
- Endpoint: GET `/cross-market/analysis`

### interpret_causality

- Rule-based causality engine
- 5 rules: bond yield, crude, USD/INR, VIX, gold
- Returns: `signal_name`, `impact`, `affected_sectors`, `severity` (low/medium/high)

## Troubleshooting

- If tools are not showing: check that the `python` path and project path in the config are correct.
- If import errors occur: ensure all pip packages are installed in the same environment used by Claude Desktop.
- If data errors appear: some scraped sources (Chittorgarh, Investorgain, World Bank) may be temporarily down.

