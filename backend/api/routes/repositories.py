import logging
import re
import uuid
from pathlib import Path

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

# Single source of truth for orchestrator order (must match ``run_analysis_task``).
# Documentation runs before tech debt so a tech-debt failure does not skip generated docs/services.
WORKFLOW_SEQUENCE: List[str] = [
    "planning_agent",
    "code_browser_agent",
    "dependency_mapper_agent",
    "documentation_agent",
    "tech_debt_agent",
    "impact_agent",
    "human_review_agent",
]
WORKFLOW_AGENT_COUNT = len(WORKFLOW_SEQUENCE)


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
    if st in ("cloning", "queued"):
        # Preserve clone / queue progress (e.g. 0.02 cloning, 0.05 ready to analyze)
        return min(1.0, float(analysis.get("progress", 0.0)))
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
    # Fine-grained or classic PAT with repo scope; used only for this clone (not stored).
    github_token: Optional[str] = None


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


def _derive_repository_name(payload: RepositoryAnalyzeRequest) -> str:
    """Short display name for the repositories row (DB + UI)."""
    if payload.github_repo and str(payload.github_repo).strip():
        return str(payload.github_repo).strip()
    if payload.repository_url and str(payload.repository_url).strip():
        url = str(payload.repository_url).strip()
        m = re.search(r"github\.com/([^/]+)/([^/.?#]+)", url, re.IGNORECASE)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
        base = url.rstrip("/").split("/")[-1]
        if base.endswith(".git"):
            base = base[:-4]
        return (base or "repository")[:180]
    if payload.repository_path and str(payload.repository_path).strip():
        return Path(str(payload.repository_path).strip()).name or "repository"
    return "repository"


def _derive_github_coords(payload: RepositoryAnalyzeRequest) -> tuple[Optional[str], Optional[str]]:
    """Preserve owner/repo metadata for GitHub URLs so temporal PR fetching works later."""
    owner = (payload.github_owner or "").strip() or None
    repo = (payload.github_repo or "").strip() or None
    if owner and repo:
        return owner, repo
    if payload.repository_url and str(payload.repository_url).strip():
        url = str(payload.repository_url).strip()
        m = re.search(r"github\.com/([^/]+)/([^/.?#]+)", url, re.IGNORECASE)
        if m:
            return m.group(1), m.group(2)
    return owner, repo


def _payload_to_dict(payload: RepositoryAnalyzeRequest) -> dict:
    gh_owner, gh_repo = _derive_github_coords(payload)
    return {
        "repository_url": payload.repository_url,
        "repository_path": payload.repository_path,
        "github_owner": gh_owner,
        "github_repo": gh_repo,
        "branch": payload.branch,
    }


def run_clone_and_analysis_task(repository_id: str, payload_dict: dict) -> None:
    """
    Clone (or attach local path) in the background so POST /analyze returns immediately.
    Avoids HTTP/proxy timeouts on large repositories (e.g. CodeIgniter).
    """
    branch = (payload_dict.get("branch") or "").strip() or None
    try:
        active_analyses[repository_id] = {
            "status": "cloning",
            "progress": 0.02,
            "message": "Cloning repository…",
        }
        _persist_repository_status(
            repository_id,
            "cloning",
            0.02,
            "Cloning repository…",
        )

        raw_gh_tok = payload_dict.get("github_token")
        gh_tok_s = (
            str(raw_gh_tok).strip() if raw_gh_tok is not None else None
        ) or None

        if payload_dict.get("github_owner") and payload_dict.get("github_repo"):
            repo_path = repo_manager.clone_from_github(
                str(payload_dict["github_owner"]).strip(),
                str(payload_dict["github_repo"]).strip(),
                branch,
                github_token=gh_tok_s,
            )
        elif payload_dict.get("repository_url"):
            repo_path = repo_manager.clone_from_url(
                str(payload_dict["repository_url"]).strip(),
                branch,
                github_token=gh_tok_s,
            )
        elif payload_dict.get("repository_path"):
            repo_path = repo_manager.use_local_path(str(payload_dict["repository_path"]).strip())
        else:
            raise ValueError("Invalid clone payload")

        db = SessionLocal()
        try:
            row = db.query(Repository).filter(Repository.id == repository_id).first()
            if row:
                row.local_path = repo_path
                if branch:
                    row.branch = branch
                row.status = "running"
                row.progress = 0.05
                row.message = "Starting analysis"
                db.commit()
        finally:
            db.close()

        active_analyses[repository_id] = {
            "status": "running",
            "progress": 0.05,
            "message": "Starting analysis",
        }
        run_analysis_task(repository_id, repo_path)
    except ValueError as e:
        msg = str(e)
        logger.warning("Clone failed for %s: %s", repository_id[:12], msg)
        active_analyses[repository_id] = {
            "status": "failed",
            "progress": 0.0,
            "message": msg,
        }
        _persist_repository_status(repository_id, "failed", 0.0, msg)
    except Exception as e:
        msg = f"Clone or setup failed: {e}"
        logger.exception("run_clone_and_analysis_task failed for %s", repository_id[:12])
        active_analyses[repository_id] = {
            "status": "failed",
            "progress": 0.0,
            "message": msg,
        }
        _persist_repository_status(repository_id, "failed", 0.0, msg)


def run_analysis_task(repository_id: str, repo_path: str):
    """Background task to run analysis."""
    run_id: Optional[str] = None
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
        _persist_repository_status(repository_id, "running", 0.05, "Preparing workflow")
        
        result = orchestrator.execute_workflow(run_id, list(WORKFLOW_SEQUENCE))

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
        previous = active_analyses.get(repository_id, {})
        active_analyses[repository_id] = {
            "status": "failed",
            "run_id": run_id or previous.get("run_id"),
            "progress": previous.get("progress", 0.0),
            "message": f"Analysis failed: {str(e)}",
            "error": str(e),
        }
        if run_id:
            run = orchestrator.get_run(run_id)
            if run and str(run.get("status", "")).lower() == "completed":
                active_analyses[repository_id]["progress"] = 1.0
        _persist_repository_status(
            repository_id,
            "failed",
            float(active_analyses[repository_id].get("progress", 0.0) or 0.0),
            active_analyses[repository_id].get("message"),
        )


@router.post("/analyze")
@limiter.limit("10/minute")
async def analyze_repository(
    request: Request,
    payload: RepositoryAnalyzeRequest,
    background_tasks: BackgroundTasks,
    api_key: bool = Depends(verify_api_key)
):
    """Start repository analysis. Clone runs in the background so this returns quickly."""
    repository_id = str(uuid.uuid4())

    if not (
        (payload.github_owner and payload.github_repo)
        or payload.repository_url
        or payload.repository_path
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide repository_url, repository_path, or github_owner/github_repo",
        )

    branch_label = (payload.branch or "").strip() or "main"
    display_name = _derive_repository_name(payload)
    gh_owner, gh_repo = _derive_github_coords(payload)

    db = SessionLocal()
    try:
        repo = Repository(
            id=repository_id,
            name=display_name,
            url=payload.repository_url,
            local_path=None,
            github_owner=gh_owner,
            github_repo=gh_repo,
            branch=branch_label,
            status="cloning",
            progress=0.02,
            message="Cloning repository…",
        )
        db.add(repo)
        db.commit()
    finally:
        db.close()

    active_analyses[repository_id] = {
        "status": "cloning",
        "progress": 0.02,
        "message": "Cloning repository…",
    }

    background_tasks.add_task(
        run_clone_and_analysis_task,
        repository_id,
        payload.model_dump(),
    )

    return {
        "repository_id": repository_id,
        "status": "cloning",
        "message": "Repository clone started; poll status for progress.",
    }


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
                analysis["completed_agents"] = [str(x) for x in completed if x]
                analysis["workflow"] = list(WORKFLOW_SEQUENCE)
                current_agent = run.get("current_agent")
                analysis["current_agent"] = str(current_agent) if current_agent else None
                if current_agent:
                    analysis["status"] = "running"
                    analysis["message"] = (
                        f"Running {_agent_label(str(current_agent))} "
                        f"({completed_count}/{WORKFLOW_AGENT_COUNT})"
                    )
                elif str(run.get("status", "")).lower() == "completed" and analysis.get("status") not in ("failed", "error"):
                    analysis["status"] = "completed"
                    analysis["message"] = "Analysis completed"
                    analysis["progress"] = 1.0
                elif analysis.get("status") in ("failed", "error"):
                    analysis["progress"] = max(
                        float(analysis.get("progress", 0.0) or 0.0),
                        min(1.0, completed_count / WORKFLOW_AGENT_COUNT),
                    )
        if analysis.get("status") not in ("running", "completed"):
            analysis["progress"] = _workflow_progress_from_analysis(analysis)

        return {
            "repository_id": repository_id,
            "repository_name": _get_repository_name(repository_id),
            "status": analysis.get("status", "unknown"),
            "progress": analysis.get("progress", 0.0),
            "message": analysis.get("message"),
            "workflow": analysis.get("workflow") or list(WORKFLOW_SEQUENCE),
            "completed_agents": analysis.get("completed_agents") or [],
            "current_agent": analysis.get("current_agent"),
            "agent_total": WORKFLOW_AGENT_COUNT,
        }

    db = SessionLocal()
    try:
        repo = db.query(Repository).filter(Repository.id == repository_id).first()
        if repo:
            st = (repo.status or "unknown").lower()
            done = st in ("completed", "complete", "success", "done")
            return {
                "repository_id": repository_id,
                "repository_name": repo.name,
                "status": repo.status or "unknown",
                "progress": float(repo.progress) if repo.progress is not None else 0.0,
                "message": repo.message,
                "workflow": list(WORKFLOW_SEQUENCE),
                "completed_agents": list(WORKFLOW_SEQUENCE) if done else [],
                "current_agent": None,
                "agent_total": WORKFLOW_AGENT_COUNT,
            }
    finally:
        db.close()

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Repository analysis not found",
    )


@router.get("")
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
