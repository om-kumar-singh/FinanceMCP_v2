"""
AI query API routes.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.query_service import process_query

query_router = APIRouter(tags=["query"])


class QueryRequest(BaseModel):
    """Request body for /ask endpoint."""

    query: str


@query_router.post("/ask")
def ask_query(request: QueryRequest):
    """
    Process natural language financial query.

    Request body: {"query": "What is RSI of Reliance?"}

    Example: POST /ask with {"query": "What is the stock price of TCS?"}
    """
    try:
        result = process_query(request.query)
        return result
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing the query.",
        )
