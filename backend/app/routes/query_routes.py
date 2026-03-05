"""
AI query API routes.
"""

import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.services.chat_advisor_service import handle_chat_query
from app.services.conversation_memory import get_context, update_context

logger = logging.getLogger(__name__)

query_router = APIRouter(tags=["query"])


class QueryRequest(BaseModel):
    """Request body for /ask endpoint."""

    query: str
    watchlist: list[dict] | None = None


@query_router.post("/ask")
async def ask_query(request: Request, body: QueryRequest):
    """
    Process natural language financial query.

    Request body: {"query": "What is RSI of Reliance?"}

    Example: POST /ask with {"query": "What is the stock price of TCS?"}
    """
    client_id = request.headers.get("X-Session-Id") or (request.client.host if request.client else None) or "anonymous"
    ctx = get_context(client_id)
    try:
        payload, updates = await handle_chat_query(body.query, context=ctx)
        if updates:
            update_context(client_id, **updates)
        return payload
    except Exception:
        logger.error("Ask API failed", exc_info=True)
        return {"message": "AI advisor is temporarily unavailable."}


@query_router.post("/chat")
async def chat(request: Request, body: QueryRequest):
    """
    Chat endpoint for the AI advisor. Same as /ask; accepts {"query": "user message"}.
    """
    client_id = request.headers.get("X-Session-Id") or (request.client.host if request.client else None) or "anonymous"
    ctx = get_context(client_id)
    try:
        payload, updates = await handle_chat_query(body.query, context=ctx)
        if updates:
            update_context(client_id, **updates)
        return payload
    except Exception:
        logger.error("Chat API failed", exc_info=True)
        return {"message": "AI advisor is temporarily unavailable."}
