import uuid
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from core.security import verify_api_key
from api.middleware.rate_limit import get_rate_limiter, limiter
from services.repository_manager import RepositoryManager
from services.agent_orchestrator import AgentOrchestrator
from agents.planning_agent import PlanningAgent
from agents.code_browser_agent import CodeBrowserAgent
from agents.dependency_mapper_agent import DependencyMapperAgent
from agents.documentation_agent import DocumentationAgent
from agents.impact_agent import ImpactAgent
from agents.human_review_agent import HumanReviewAgent

router = APIRouter()

# Initialize services
repo_manager = RepositoryManager()
orchestrator = AgentOrchestrator()

# Register agents
orchestrator.register_agent(PlanningAgent())
orchestrator.register_agent(CodeBrowserAgent())
orchestrator.register_agent(DependencyMapperAgent())
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


def run_analysis_task(repository_id: str, repo_path: str):
    """Background task to run analysis."""
    try:
        run_id = orchestrator.create_run(repository_id, {
            "repository_path": repo_path,
            "repository_id": repository_id,
        })
        
        # Execute workflow
        workflow = ["planning_agent", "code_browser_agent", "dependency_mapper_agent", 
                    "documentation_agent", "impact_agent", "human_review_agent"]
        
        result = orchestrator.execute_workflow(run_id, workflow)
        
        active_analyses[repository_id] = {
            "status": result["status"],
            "run_id": run_id,
            "result": result,
        }
    except Exception as e:
        active_analyses[repository_id] = {
            "status": "failed",
            "error": str(e),
        }


@router.post("/analyze")
@limiter.limit("10/minute")
async def analyze_repository(
    request: RepositoryAnalyzeRequest,
    background_tasks: BackgroundTasks,
    api_key: bool = Depends(verify_api_key)
):
    """Start repository analysis."""
    repository_id = str(uuid.uuid4())
    repo_path = None
    
    try:
        # Determine repository source and clone/use it
        if request.github_owner and request.github_repo:
            repo_path = repo_manager.clone_from_github(
                request.github_owner,
                request.github_repo,
                request.branch
            )
        elif request.repository_url:
            repo_path = repo_manager.clone_from_url(
                request.repository_url,
                request.branch
            )
        elif request.repository_path:
            repo_path = repo_manager.use_local_path(request.repository_path)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Must provide repository_url, repository_path, or github_owner/github_repo"
            )
        
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
    """Get analysis status for a repository."""
    if repository_id not in active_analyses:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository analysis not found"
        )
    
    analysis = active_analyses[repository_id]
    
    # Get run status if available
    if "run_id" in analysis:
        run = orchestrator.get_run(analysis["run_id"])
        if run:
            analysis["progress"] = 0.5  # Simplified progress
            analysis["checkpoints"] = run["state"].checkpoints
    
    return {
        "repository_id": repository_id,
        "status": analysis.get("status", "unknown"),
        "progress": analysis.get("progress", 0.0),
        "message": analysis.get("message"),
    }


@router.get("/")
async def list_repositories(
    api_key: bool = Depends(verify_api_key)
):
    """List all analyzed repositories."""
    repositories = []
    for repo_id, analysis in active_analyses.items():
        repositories.append({
            "id": repo_id,
            "status": analysis.get("status", "unknown"),
            "progress": analysis.get("progress", 0.0),
        })
    
    return {"repositories": repositories}
