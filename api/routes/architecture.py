"""Architecture overview: static analysis + LLM narrative, cached per repository."""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.middleware.rate_limit import limiter
from core.database import get_db
from core.security import verify_api_key
from models.repository import Repository
from services.architecture_analyzer import run_static_architecture_analysis
from services.architecture_llm import enrich_architecture_narrative
from services.repository_scope import resolve_repository_id

logger = logging.getLogger(__name__)

router = APIRouter()

CACHE_PREFIX = "architecture:report:v4:"
CACHE_TTL_SEC = 7 * 24 * 3600


class ArchitectureAnalyzeRequest(BaseModel):
    repository_id: str = Field(..., min_length=1, max_length=256)
    force_refresh: bool = False


def _cache_key(repository_id: str) -> str:
    return f"{CACHE_PREFIX}{repository_id}"


def _fingerprint(repo_path: str) -> str:
    try:
        raw = f"{repo_path}:{datetime.now(timezone.utc).date().isoformat()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
    except Exception:
        return "unknown"


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
        logger.info("architecture cache get skipped: %s", exc)
        return None


def _cache_set(key: str, payload: Dict[str, Any]) -> None:
    try:
        from core.database import get_redis_client

        r = get_redis_client()
        r.setex(key, CACHE_TTL_SEC, json.dumps(payload, default=str))
    except Exception as exc:
        logger.info("architecture cache set skipped: %s", exc)


def _build_report(
    db: Session,
    repository_id: str,
    *,
    force_refresh: bool,
) -> Dict[str, Any]:
    resolved = resolve_repository_id(db, repository_id) or repository_id
    repo = db.query(Repository).filter(Repository.id == resolved).first()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )
    if not repo.local_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository has no local clone path. Run analysis first.",
        )

    key = _cache_key(resolved)
    if not force_refresh:
        cached = _cache_get(key)
        if cached:
            logger.info("architecture cache hit repo=%s", resolved[:12])
            return cached

    if force_refresh:
        logger.info("architecture force refresh repo=%s", resolved[:12])

    static = run_static_architecture_analysis(resolved, repo.local_path)
    narrative = enrich_architecture_narrative(static)

    report: Dict[str, Any] = {
        **static,
        "narrative": narrative,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cache_fingerprint": _fingerprint(repo.local_path),
    }
    _cache_set(key, report)
    logger.info(
        "architecture report stored repo=%s nodes=%d risks=%d",
        resolved[:12],
        len((static.get("diagram") or {}).get("nodes") or []),
        len((static.get("risks_and_practices") or {}).get("risks") or []),
    )
    return report


@router.post("/analyze")
@limiter.limit("8/minute")
async def analyze_architecture(
    request: Request,
    body: ArchitectureAnalyzeRequest,
    db: Session = Depends(get_db),
    api_key: bool = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Recompute architecture analysis and refresh cache."""
    return _build_report(db, body.repository_id, force_refresh=body.force_refresh)


@router.get("/{repository_id}")
@limiter.limit("60/minute")
async def get_architecture(
    request: Request,
    repository_id: str,
    db: Session = Depends(get_db),
    api_key: bool = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Return cached architecture report (does not re-scan disk unless cache miss)."""
    return _build_report(db, repository_id, force_refresh=False)

