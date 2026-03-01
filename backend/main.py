"""
BharatFinanceAI - FastAPI Backend
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.ipo_routes import ipo_router
from app.routes.macro_routes import macro_router
from app.routes.mutual_fund_routes import mutual_fund_router
from app.routes.query_routes import query_router
from app.routes.stock_routes import macd_router
from app.routes.stock_routes import rsi_router
from app.routes.stock_routes import router as stock_router

app = FastAPI(
    title="BharatFinanceAI",
    description="Finance AI Backend API",
    version="0.1.0",
)

# CORS configuration to allow frontend (Vite) to call the API
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stock_router)
app.include_router(rsi_router)
app.include_router(macd_router)
app.include_router(mutual_fund_router)
app.include_router(ipo_router)
app.include_router(macro_router)
app.include_router(query_router)


@app.get("/")
def root():
    """Health check and API status endpoint."""
    return {"message": "Backend is running"}
