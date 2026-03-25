import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime
from core.security import verify_api_key
from api.middleware.rate_limit import get_rate_limiter, limiter
from services.repository_manager import RepositoryManager
from services.agent_orchestrator import AgentOrchestrator
from agents.planning_agent import PlanningAgent
from agents.code_browser_agent import CodeBrowserAgent
from agents.dependency_mapper_agent import DependencyMapperAgent
from agents.tech_debt_agent import TechDebtAgent
from agents.documentation_agent import DocumentationAgent
from agents.impact_agent import ImpactAgent
from agents.human_review_agent import HumanReviewAgent

router = APIRouter()

from core.database import SessionLocal
from models.repository import Repository
from services.tech_debt_persistence import save_tech_debt_report
from services.service_persistence import persist_services_and_docs

logger = logging.getLogger(__name__)

# Must match the length of the workflow list in ``run_analysis_task``.
WORKFLOW_AGENT_COUNT = 7


def _agent_label(agent_name: str) -> str:
    return (agent_name or "").replace("_", " ").strip().title()


def _workflow_progress_from_analysis(analysis: dict) -> float:
    """Derive 0..1 progress from orchestrator result (avoids fake 50% stuck UI)."""
    res = analysis.get("result") or {}
    st = (analysis.get("status") or res.get("status") or "").lower()
    if st in ("completed", "complete", "success", "done"):
        return 1.0
    if st == "failed":
        return max(0.0, float(analysis.get("progress", 0.0)))
    if st == "paused":
        ca = res.get("completed_agents") or []
        return min(1.0, len(ca) / WORKFLOW_AGENT_COUNT)
    if st == "queued":
        return 0.0
    if "run_id" in analysis:
        ca = res.get("completed_agents")
        if ca is not None:
            return min(1.0, len(ca) / WORKFLOW_AGENT_COUNT)
    return float(analysis.get("progress", 0.0))

# Initialize services
repo_manager = RepositoryManager()
orchestrator = AgentOrchestrator()

# Register agents
orchestrator.register_agent(PlanningAgent())
orchestrator.register_agent(CodeBrowserAgent())
orchestrator.register_agent(DependencyMapperAgent())
orchestrator.register_agent(TechDebtAgent())
orchestrator.register_agent(DocumentationAgent())
orchestrator.register_agent(ImpactAgent())
orchestrator.register_agent(HumanReviewAgent())

# Store active analyses
active_analyses = {}


class RepositoryAnalyzeRequest(BaseModel):
    repository_url: Optional[str] = None
    repository_path: Optional[str] = None
    github_owner: Optional[str] = None
    github_repo: Optional[str] = None
    branch: Optional[str] = "main"


class RepositoryStatusResponse(BaseModel):
    repository_id: str
    status: str
    progress: float
    message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


def _persist_repository_status(
    repository_id: str,
    status: str,
    progress: float,
    message: Optional[str] = None,
) -> None:
    """Keep Postgres in sync so status survives API restarts."""
    db = SessionLocal()
    try:
        row = db.query(Repository).filter(Repository.id == repository_id).first()
        if row:
            row.status = status
            row.progress = progress
            if message is not None:
                row.message = message
            db.commit()
    except Exception as exc:
        logger.warning("Failed to persist repository status for %s: %s", repository_id, exc)
    finally:
        db.close()


def _get_repository_name(repository_id: str) -> Optional[str]:
    db = SessionLocal()
    try:
        row = db.query(Repository).filter(Repository.id == repository_id).first()
        return row.name if row else None
    finally:
        db.close()


def run_analysis_task(repository_id: str, repo_path: str):
    """Background task to run analysis."""
    _persist_repository_status(repository_id, "analyzing", 0.05, "Initializing analysis")
    try:
        run_id = orchestrator.create_run(repository_id, {
            "repository_path": repo_path,
            "repository_id": repository_id,
        })
        active_analyses[repository_id] = {
            "status": "running",
            "run_id": run_id,
            "progress": 0.05,
            "message": "Preparing workflow",
        }
        
        # Execute workflow
        workflow = ["planning_agent", "code_browser_agent", "dependency_mapper_agent", 
                    "tech_debt_agent", "documentation_agent", "impact_agent", "human_review_agent"]
        
        result = orchestrator.execute_workflow(run_id, workflow)

        active_analyses[repository_id] = {
            "status": result["status"],
            "run_id": run_id,
            "result": result,
            "message": "Analysis completed",
        }
        active_analyses[repository_id]["progress"] = _workflow_progress_from_analysis(
            active_analyses[repository_id]
        )

        run = orchestrator.get_run(run_id)
        if run:
            td = run["state"].get("tech_debt_analysis")
            if td:
                save_tech_debt_report(repository_id, td)
            persist_services_and_docs(
                repository_id,
                run["state"].get("services") or [],
                run["state"].get("documentation") or {},
            )

        final_status = str(result.get("status", "completed"))
        _persist_repository_status(
            repository_id,
            final_status,
            active_analyses[repository_id]["progress"],
            active_analyses[repository_id].get("message"),
        )
    except Exception as e:
        active_analyses[repository_id] = {
            "status": "failed",
            "error": str(e),
        }
        _persist_repository_status(repository_id, "failed", 0.0, str(e))


@router.post("/analyze")
@limiter.limit("10/minute")
async def analyze_repository(
    request: Request,
    payload: RepositoryAnalyzeRequest,
    background_tasks: BackgroundTasks,
    api_key: bool = Depends(verify_api_key)
):
    """Start repository analysis."""
    repository_id = str(uuid.uuid4())
    repo_path = None
    
    try:
        # Determine repository source and clone/use it
        if payload.github_owner and payload.github_repo:
            repo_path = repo_manager.clone_from_github(
                payload.github_owner,
                payload.github_repo,
                payload.branch
            )
        elif payload.repository_url:
            repo_path = repo_manager.clone_from_url(
                payload.repository_url,
                payload.branch
            )
        elif payload.repository_path:
            repo_path = repo_manager.use_local_path(payload.repository_path)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Must provide repository_url, repository_path, or github_owner/github_repo"
            )
        
        # Persist repository record so other endpoints (reports/metrics) can reference it
        db = SessionLocal()
        try:
            repo = Repository(
                id=repository_id,
                name=payload.github_repo or payload.repository_url or repository_id,
                url=payload.repository_url,
                local_path=repo_path,
                github_owner=payload.github_owner,
                github_repo=payload.github_repo,
                branch=payload.branch or "main",
                status="queued",
                progress=0.0,
            )
            db.add(repo)
            db.commit()
        finally:
            db.close()

        # Start analysis in background
        active_analyses[repository_id] = {
            "status": "queued",
            "progress": 0.0,
        }

        background_tasks.add_task(run_analysis_task, repository_id, repo_path)

        return {
            "repository_id": repository_id,
            "status": "queued",
            "message": "Analysis queued"
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start analysis: {str(e)}"
        )


@router.get("/{repository_id}/status")
async def get_analysis_status(
    repository_id: str,
    api_key: bool = Depends(verify_api_key)
):
    """Get analysis status for a repository.

    Uses in-memory ``active_analyses`` while the process is running. After a server
    restart, falls back to the persisted ``repositories`` row so the UI can still
    poll without 404 spam.
    """
    if repository_id in active_analyses:
        analysis = active_analyses[repository_id]

        if "run_id" in analysis:
            run = orchestrator.get_run(analysis["run_id"])
            if run:
                analysis["checkpoints"] = run["state"].checkpoints
                completed: List[Any] = run.get("completed_agents") or []
                completed_count = len(completed)
                analysis["progress"] = min(1.0, completed_count / WORKFLOW_AGENT_COUNT)
                current_agent = run.get("current_agent")
                if current_agent:
                    analysis["status"] = "running"
                    analysis["message"] = (
                        f"Running {_agent_label(str(current_agent))} "
                        f"({completed_count}/{WORKFLOW_AGENT_COUNT})"
                    )
                elif str(run.get("status", "")).lower() == "completed":
                    analysis["status"] = "completed"
                    analysis["message"] = "Analysis completed"
                    analysis["progress"] = 1.0
                elif analysis.get("status") == "queued":
                    analysis["message"] = "Queued"
        if analysis.get("status") not in ("running", "completed"):
            analysis["progress"] = _workflow_progress_from_analysis(analysis)

        return {
            "repository_id": repository_id,
            "repository_name": _get_repository_name(repository_id),
            "status": analysis.get("status", "unknown"),
            "progress": analysis.get("progress", 0.0),
            "message": analysis.get("message"),
        }

    db = SessionLocal()
    try:
        repo = db.query(Repository).filter(Repository.id == repository_id).first()
        if repo:
            return {
                "repository_id": repository_id,
                "repository_name": repo.name,
                "status": repo.status or "unknown",
                "progress": float(repo.progress) if repo.progress is not None else 0.0,
                "message": repo.message,
            }
    finally:
        db.close()

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Repository analysis not found",
    )


@router.get("/")
async def list_repositories(
    api_key: bool = Depends(verify_api_key)
):
    """List analyzed repositories (in-memory session + persisted rows)."""
    seen: set[str] = set()
    repositories = []
    for repo_id, analysis in active_analyses.items():
        seen.add(repo_id)
        repositories.append({
            "id": repo_id,
            "name": _get_repository_name(repo_id),
            "status": analysis.get("status", "unknown"),
            "progress": analysis.get("progress", 0.0),
        })

    db = SessionLocal()
    try:
        for row in db.query(Repository).order_by(Repository.created_at.desc()).limit(100).all():
            if row.id in seen:
                continue
            repositories.append({
                "id": row.id,
                "status": row.status or "unknown",
                "progress": float(row.progress) if row.progress is not None else 0.0,
                "name": row.name,
            })
    finally:
        db.close()

    return {"repositories": repositories}
