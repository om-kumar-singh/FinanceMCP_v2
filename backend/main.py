"""
BharatFinanceAI - FastAPI Backend
"""

import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.routes.compare_routes import compare_router
from app.routes.history_routes import history_router
from app.routes.ipo_routes import ipo_router
from app.routes.macro_routes import macro_router
from app.routes.mutual_fund_routes import mutual_fund_router
from app.routes.portfolio_routes import portfolio_router
from app.routes.news_routes import news_router
from app.routes.query_routes import query_router
from app.routes.sector_routes import sector_router
from app.routes.stock_routes import bollinger_router
from app.routes.stock_routes import gainers_losers_router
from app.routes.stock_routes import macd_router
from app.routes.stock_routes import moving_averages_router
from app.routes.stock_routes import rsi_router
from app.routes.stock_routes import router as stock_router
from app.routes.advisor_v2_routes import advisor_v2_router
from app.routes.advisor_v3_routes import advisor_v3_router
from app.routes.advisor_v4_routes import advisor_v4_router
from app.routes.advisor_v5_routes import advisor_v5_router
from app.routes.advisor_v3_routes import advisor_v3_router
from app.services.stock_search_service import initialize_stock_database
from app.utils.response_optimizer import MAX_RESPONSE_SIZE, optimize_response


# Load backend environment variables from backend/.env if present.
# This ensures GEMINI_API_KEY (and other secrets) are available when running locally.
_env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=_env_path, override=False)


class ResponseOptimizerMiddleware(BaseHTTPMiddleware):
    """
    Middleware to adaptively shrink large JSON responses.
    """

    async def dispatch(self, request, call_next):
        response = await call_next(request)

        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        size_bytes = len(body)
        size_kb = round(size_bytes / 1024, 2)
        headers = dict(response.headers)
        headers["X-Response-Size-KB"] = str(size_kb)

        if size_bytes <= MAX_RESPONSE_SIZE:
            return Response(
                content=body,
                status_code=response.status_code,
                headers=headers,
                media_type=response.media_type,
            )

        try:
            data = json.loads(body)
        except Exception:
            # Not JSON or cannot decode; return as-is with size header
            return Response(
                content=body,
                status_code=response.status_code,
                headers=headers,
                media_type=response.media_type,
            )

        optimized = optimize_response(data)
        optimized_bytes = json.dumps(optimized).encode("utf-8")
        headers["X-Response-Optimized"] = "true"
        headers["X-Response-Size-KB"] = str(round(len(optimized_bytes) / 1024, 2))

        return Response(
            content=optimized_bytes,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type,
        )


app = FastAPI(
    title="BharatFinanceAI",
    description="Finance AI Backend API",
    version="0.1.0",
)

# CORS: use CORS_ORIGINS env var (comma-separated) for production.
# For local development, allow common Vite dev ports on localhost.
_default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:5175",
    "http://127.0.0.1:5175",
    "http://localhost:5176",
    "http://127.0.0.1:5176",
    "http://localhost:5177",
    "http://127.0.0.1:5177",
    "http://localhost:5178",
    "http://127.0.0.1:5178",
]
_cors_origins = os.getenv("CORS_ORIGINS", "").strip()
origins = [o.strip() for o in _cors_origins.split(",") if o.strip()] or _default_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ResponseOptimizerMiddleware)

app.include_router(compare_router)
app.include_router(history_router)
app.include_router(stock_router)
app.include_router(rsi_router)
app.include_router(macd_router)
app.include_router(gainers_losers_router)
app.include_router(moving_averages_router)
app.include_router(bollinger_router)
app.include_router(mutual_fund_router)
app.include_router(ipo_router)
app.include_router(macro_router)
app.include_router(query_router)
app.include_router(sector_router)
app.include_router(portfolio_router)
app.include_router(news_router)
app.include_router(advisor_v2_router)
app.include_router(advisor_v3_router)
app.include_router(advisor_v4_router)
app.include_router(advisor_v5_router)
app.include_router(advisor_v3_router)

# Resilience router: lazy-loaded. Import only when including; if it fails, other APIs unaffected.
try:
    from app.routers.resilience import resilience_router
    app.include_router(resilience_router)
except Exception as e:
    print("Resilience module skipped (other APIs unaffected):", e)


@app.on_event("startup")
async def startup_event() -> None:
    # Preload NSE stock database for fast search and resolution
    try:
        initialize_stock_database()
    except Exception:
        # Fail silently; fallback list will be used when searched
        pass


@app.get("/")
def root():
    """Health check and API status endpoint."""
    return {"message": "Backend is running"}


@app.get("/mcp-info")
def mcp_info():
    """Info about the MCP server and available tools."""
    return {
        "project": "BharatFinanceMCP",
        "description": "Indian Financial Markets MCP Server",
        "mcp_server": "backend/mcp_server.py",
        "claude_desktop_setup": "docs/mcp_setup.md",
        "total_tools": 22,
        "tools": [
            "get_stock_quote",
            "calculate_rsi",
            "calculate_macd",
            "calculate_bollinger_bands",
            "calculate_moving_averages",
            "get_top_gainers_losers",
            "get_market_news",
            "get_mutual_fund_nav",
            "search_mutual_funds",
            "calculate_sip",
            "calculate_capital_gains",
            "get_upcoming_ipos",
            "get_gmp",
            "get_ipo_performance",
            "get_sme_stock_analysis",
            "get_repo_rate",
            "get_inflation",
            "get_gdp_growth",
            "get_sector_performance_tool",
            "get_all_sectors_summary_tool",
            "analyze_portfolio_tool",
        ],
        "data_sources": [
            "yfinance (NSE/BSE stocks)",
            "mfapi.in (Mutual Funds)",
            "Chittorgarh.com (IPOs)",
            "investorgain.com (GMP)",
            "World Bank API (Macro)",
        ],
        "total_cost": "₹0 - Completely Free",
    }
