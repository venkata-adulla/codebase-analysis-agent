"""Cross-repository comparison API (reuses cached architecture + DB + graph)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from api.middleware.rate_limit import limiter
from core.database import get_db
from core.security import verify_api_key
from services.cross_repo_comparison import build_cross_repo_comparison
from services.cross_repo_llm import enrich_cross_repo_llm

logger = logging.getLogger(__name__)

router = APIRouter()


class CompareReposRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    repo_ids: list[str] = Field(
        ...,
        min_length=2,
        alias="repoIds",
        description="Two or more repository UUIDs to compare",
    )


@router.post("/compare-repos")
@limiter.limit("20/minute")
async def compare_repositories(
    request: Request,
    body: CompareReposRequest,
    db: Session = Depends(get_db),
    api_key: bool = Depends(verify_api_key),
) -> dict:
    """
    Structured side-by-side comparison + normalized scores + AI narrative.
    Reuses Redis-cached architecture reports, latest tech debt report, and Neo4j graph metrics.
    """
    ids = [str(x).strip() for x in body.repo_ids if str(x).strip()]
    if len(ids) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least two repository IDs are required",
        )

    logger.info("compare-repos: repoIds=%s", ids)

    try:
        built = build_cross_repo_comparison(db, ids)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    insights = enrich_cross_repo_llm(built["llm_context"])

    return {
        "comparison": built["comparison"],
        "scores": built["scores"],
        "insights": insights,
    }
