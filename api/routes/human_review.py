from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
from core.security import verify_api_key

router = APIRouter()


class HumanReviewCheckpoint(BaseModel):
    checkpoint_id: str
    agent_name: str
    question: str
    context: Dict[str, Any]
    options: Optional[List[str]] = None
    created_at: datetime
    status: str  # pending, resolved


class ResolveCheckpointBody(BaseModel):
    response: str
    metadata: Optional[Dict[str, Any]] = None


def _get_orchestrator():
    from api.routes.repositories import orchestrator
    return orchestrator


def _collect_checkpoints(
    status_filter: Optional[str] = None,
    repository_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Gather checkpoints from all active orchestrator runs."""
    orch = _get_orchestrator()
    results: List[Dict[str, Any]] = []
    for run_id, run in orch.active_runs.items():
        if repository_id and run.get("repository_id") != repository_id:
            continue
        for cp in run["state"].checkpoints:
            if status_filter and cp.get("status") != status_filter:
                continue
            results.append({
                "id": cp.get("id"),
                "run_id": run_id,
                "repository_id": run.get("repository_id"),
                "agent": cp.get("agent", ""),
                "reason": cp.get("reason", ""),
                "question": cp.get("question", ""),
                "options": cp.get("options"),
                "status": cp.get("status", "pending"),
                "timestamp": cp.get("timestamp"),
                "response": cp.get("response"),
                "context": cp.get("context") or {},
            })
    return results


@router.get("/checkpoints")
async def list_checkpoints(
    status: Optional[str] = None,
    repository_id: Optional[str] = Query(None),
    api_key: bool = Depends(verify_api_key)
):
    """List human review checkpoints."""
    return {"checkpoints": _collect_checkpoints(status, repository_id)}


@router.get("/checkpoints/{checkpoint_id}")
async def get_checkpoint(
    checkpoint_id: str,
    api_key: bool = Depends(verify_api_key)
):
    """Get human review checkpoint details."""
    for cp in _collect_checkpoints():
        if cp["id"] == checkpoint_id:
            return cp
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checkpoint not found")


@router.post("/checkpoints/{checkpoint_id}/resolve")
async def resolve_checkpoint(
    checkpoint_id: str,
    body: ResolveCheckpointBody,
    api_key: bool = Depends(verify_api_key),
):
    """Resolve a human review checkpoint; JSON body must include ``response`` (chosen option text)."""
    orch = _get_orchestrator()
    for run_id, run in orch.active_runs.items():
        for cp in run["state"].checkpoints:
            if cp.get("id") == checkpoint_id:
                try:
                    orch.resolve_checkpoint(
                        run_id,
                        checkpoint_id,
                        body.response,
                        body.metadata,
                    )
                except ValueError:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Checkpoint not found",
                    )
                return {"checkpoint_id": checkpoint_id, "status": "resolved"}
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checkpoint not found")
