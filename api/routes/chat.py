"""Codebase-aware chat: RAG retrieval + grounded LLM answers."""

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.middleware.rate_limit import limiter
from core.security import verify_api_key
from services import codebase_chat_service as chat_svc

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=8000)
    repoId: str = Field(..., min_length=1, max_length=256)
    history: Optional[List[ChatMessage]] = None
    use_cache: bool = True


class RelatedNode(BaseModel):
    id: str
    name: str
    reason: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    summary: str = ""
    detailed: str = ""
    impact: Optional[str] = None
    relatedNodes: List[RelatedNode]
    confidence: float


def _history_dicts(history: Optional[List[ChatMessage]]) -> List[Dict[str, str]]:
    if not history:
        return []
    out: List[Dict[str, str]] = []
    for m in history:
        if m.role in ("user", "assistant") and m.content.strip():
            out.append({"role": m.role, "content": m.content.strip()})
    return out


def _build_related_nodes(
    retrieved: List[Dict[str, Any]], result: Dict[str, Any]
) -> List[RelatedNode]:
    seen: set[str] = set()
    out: List[RelatedNode] = []
    for s in retrieved[:12]:
        sid = str(s.get("id") or "")
        if sid and sid not in seen:
            seen.add(sid)
            out.append(
                RelatedNode(
                    id=sid,
                    name=str(s.get("name") or sid),
                    reason="Retrieved as top relevant context for the question.",
                )
            )
    for r in result.get("related_modules") or []:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("id") or "")
        if not rid or rid in seen:
            continue
        seen.add(rid)
        out.append(
            RelatedNode(
                id=rid,
                name=str(r.get("name") or rid),
                reason=str(r.get("reason") or "").strip() or None,
            )
        )
    return out[:24]


@router.post("/", response_model=ChatResponse)
@limiter.limit("30/minute")
async def chat(
    request: Request,
    body: ChatRequest,
    api_key: bool = Depends(verify_api_key),
) -> ChatResponse:
    """
    Grounded Q&A over analyzed services and the dependency graph.
    Uses embedding retrieval + Neo4j edge context; answers must follow retrieved context.
    """
    q = body.query.strip()
    repo = body.repoId.strip()
    hist = _history_dicts(body.history)

    cache_key = chat_svc.cache_key(repo, q)
    if body.use_cache:
        cached = chat_svc.cache_get(cache_key)
        if cached:
            try:
                data = json.loads(cached)
                logger.info("Chat cache hit repo=%s", repo[:16])
                return ChatResponse(**data)
            except (json.JSONDecodeError, TypeError):
                pass

    try:
        context_block, retrieved, debug_info = chat_svc.retrieve_context(repo, q)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    logger.info(
        "Chat retrieval: repo=%s debug=%s context_len=%d",
        repo[:32],
        debug_info,
        len(context_block),
    )

    if not context_block.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No retrieval context available for this repository.",
        )

    try:
        result = chat_svc.generate_answer(q, context_block, hist)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    related_nodes = _build_related_nodes(retrieved, result)
    payload = {
        "answer": result["answer"],
        "summary": result.get("summary") or "",
        "detailed": result.get("detailed") or "",
        "impact": result.get("impact"),
        "relatedNodes": [n.model_dump() for n in related_nodes],
        "confidence": result.get("confidence") or 0.0,
    }
    chat_svc.cache_set(cache_key, json.dumps(payload))
    logger.info(
        "Chat response: confidence=%s related_nodes=%d",
        payload["confidence"],
        len(related_nodes),
    )
    return ChatResponse(**payload)


class ChatStreamRequest(ChatRequest):
    """Same as ChatRequest; separate model for OpenAPI clarity."""


@router.post("/stream")
@limiter.limit("30/minute")
async def chat_stream(
    request: Request,
    body: ChatStreamRequest,
    api_key: bool = Depends(verify_api_key),
):
    """SSE token stream (markdown). Retrieval runs once; then the model streams."""
    q = body.query.strip()
    repo = body.repoId.strip()
    hist = _history_dicts(body.history)

    try:
        context_block, retrieved, debug_info = chat_svc.retrieve_context(repo, q)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    logger.info(
        "Chat stream retrieval: repo=%s debug=%s retrieved=%d",
        repo[:32],
        debug_info,
        len(retrieved),
    )

    if not context_block.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No retrieval context available for this repository.",
        )

    def gen():
        try:
            meta = {
                "type": "meta",
                "relatedNodes": [
                    {"id": str(s.get("id")), "name": str(s.get("name") or "")}
                    for s in retrieved[:12]
                    if s.get("id")
                ],
            }
            yield f"data: {json.dumps(meta)}\n\n"
            for chunk in chat_svc.stream_answer_tokens(q, context_block, hist):
                yield f"data: {json.dumps({'type': 'token', 'chunk': chunk})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except RuntimeError as exc:
            err = {"type": "error", "message": str(exc)}
            yield f"data: {json.dumps(err)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
