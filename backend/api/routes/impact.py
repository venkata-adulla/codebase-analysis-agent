from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime

from core.database import SessionLocal
from core.security import verify_api_key
from services.repository_scope import resolve_repository_id

router = APIRouter()


class ImpactAnalysisRequest(BaseModel):
    repository_id: str
    change_description: str
    affected_files: Optional[List[str]] = None
    affected_services: Optional[List[str]] = None


class ImpactedService(BaseModel):
    service_id: str
    service_name: str
    impact_score: float
    impact_type: str
    reason: str
    affected_endpoints: List[str] = []


class ImpactAnalysisResponse(BaseModel):
    analysis_id: str
    repository_id: str
    change_description: str
    impacted_services: List[ImpactedService]
    risk_level: str
    recommendations: List[str] = []
    created_at: datetime


@router.post("/analyze")
async def run_impact_analysis(
    request: ImpactAnalysisRequest,
    api_key: bool = Depends(verify_api_key)
):
    """Run impact analysis for a change."""
    import uuid
    from services.impact_engine import ImpactEngine
    from datetime import datetime
    
    impact_engine = ImpactEngine()

    db = SessionLocal()
    try:
        canonical_repo_id = resolve_repository_id(db, request.repository_id) or request.repository_id
    finally:
        db.close()

    result = impact_engine.analyze_impact(
        repository_id=canonical_repo_id,
        change_description=request.change_description,
        affected_files=request.affected_files,
        affected_services=request.affected_services,
    )
    
    analysis_id = str(uuid.uuid4())
    
    return {
        "analysis_id": analysis_id,
        "repository_id": canonical_repo_id,
        "repository_id_requested": request.repository_id,
        "change_description": request.change_description,
        "impacted_services": result["impacted_services"],
        "risk_level": result["risk_level"],
        "recommendations": result["recommendations"],
        "total_impacted": result["total_impacted"],
        "risk_summary": result.get("risk_summary") or "",
        "global_what_could_break": result.get("global_what_could_break") or [],
        "created_at": datetime.utcnow(),
    }


@router.get("/{analysis_id}")
async def get_impact_analysis(
    analysis_id: str,
    api_key: bool = Depends(verify_api_key)
):
    """Get impact analysis results."""
    # TODO: Implement impact analysis retrieval
    return {
        "analysis_id": analysis_id,
        "impacted_services": []
    }
