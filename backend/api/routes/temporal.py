"""Temporal view / drift analysis API."""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from api.middleware.rate_limit import limiter
from core.database import get_db
from core.security import verify_api_key
from services.temporal_analysis import run_temporal_analysis
from services.temporal_llm import enrich_temporal_insights

logger = logging.getLogger(__name__)

router = APIRouter()

CACHE_PREFIX = "temporal:data:"
CACHE_TTL_SEC = 30 * 60


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _cache_key(parts: str) -> str:
    h = hashlib.sha256(parts.encode()).hexdigest()[:24]
    return f"{CACHE_PREFIX}{h}"


def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    try:
        from core.database import get_redis_client

        r = get_redis_client()
        v = r.get(key)
        if not v:
            return None
        if isinstance(v, bytes):
            v = v.decode("utf-8")
        return json.loads(v)
    except Exception as exc:
        logger.debug("temporal cache get: %s", exc)
        return None


def _cache_set(key: str, payload: Dict[str, Any]) -> None:
    try:
        from core.database import get_redis_client

        r = get_redis_client()
        r.setex(key, CACHE_TTL_SEC, json.dumps(payload, default=str))
    except Exception as exc:
        logger.debug("temporal cache set: %s", exc)


@router.get("/temporal-data")
@limiter.limit("40/minute")
async def get_temporal_data(
    request: Request,
    repoId: str = Query(..., alias="repoId", min_length=1),
    since: Optional[str] = Query(None, description="ISO8601 start (default: 90d ago)"),
    until: Optional[str] = Query(None, description="ISO8601 end (default: now)"),
    author: Optional[str] = Query(None, description="Filter commits by author substring"),
    module: Optional[str] = Query(None, description="Service UUID to filter commits touching it"),
    max_commits: int = Query(500, ge=50, le=2000),
    refresh: bool = Query(False, description="Bypass cache"),
    db: Session = Depends(get_db),
    api_key: bool = Depends(verify_api_key),
) -> Dict[str, Any]:
    """
    Time-based evolution: timeline, drift metrics, heatmap, PR insights, AI summaries.
    """
    since_dt = _parse_dt(since)
    until_dt = _parse_dt(until)

    cache_parts = f"{repoId}|{since or ''}|{until or ''}|{author or ''}|{module or ''}|{max_commits}"
    ck = _cache_key(cache_parts)

    if not refresh:
        cached = _cache_get(ck)
        if cached:
            logger.info("temporal cache hit repo=%s", repoId[:12])
            return cached

    try:
        base = run_temporal_analysis(
            db,
            repoId,
            since=since_dt,
            until=until_dt,
            author=author,
            module_service_id=module,
            max_commits=max_commits,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    llm_part = enrich_temporal_insights(base)
    out: Dict[str, Any] = {**base, **llm_part}
    out["cached_until"] = None
    _cache_set(ck, out)

    logger.info(
        "temporal-data: commits=%s timeline=%d",
        (out.get("debug") or {}).get("commits_processed"),
        len(out.get("timeline") or []),
    )
    return out
