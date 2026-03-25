from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from core.database import SessionLocal
from core.security import verify_api_key
from models.repository import Repository
from services.dependency_graph_fallback import graph_from_postgres_services
from services.repository_scope import resolve_repository_id

router = APIRouter()


class DependencyNode(BaseModel):
    id: str
    label: str
    type: str
    metadata: Dict[str, Any] = {}


class DependencyEdge(BaseModel):
    source: str
    target: str
    type: str
    metadata: Dict[str, Any] = {}


class DependencyGraphResponse(BaseModel):
    nodes: List[DependencyNode]
    edges: List[DependencyEdge]


@router.get("/graph")
async def get_dependency_graph(
    repository_id: Optional[str] = Query(None),
    api_key: bool = Depends(verify_api_key),
):
    """Get full dependency graph (Neo4j), scoped by resolved repository id when provided."""
    from services.graph_service import GraphService

    graph_id: Optional[str] = None
    repository_name: Optional[str] = None
    if repository_id:
        db = SessionLocal()
        try:
            graph_id = resolve_repository_id(db, repository_id)
            effective_id = graph_id or repository_id
            repo_row = db.query(Repository).filter(Repository.id == effective_id).first()
            if repo_row:
                repository_name = repo_row.name
        finally:
            db.close()
        if graph_id is None:
            graph_id = repository_id

    result: Dict[str, Any]
    try:
        graph_service = GraphService()
        result = graph_service.get_dependency_graph(graph_id)
        result.setdefault("graph_source", "neo4j")
    except Exception as exc:
        # Neo4j down or misconfigured — still allow Postgres-only visualization
        result = {
            "nodes": [],
            "edges": [],
            "graph_source": "neo4j_unavailable",
            "graph_note": str(exc),
        }

    if graph_id and not result.get("nodes"):
        fb = graph_from_postgres_services(graph_id)
        if fb:
            fb["repository_id"] = graph_id
            if repository_name:
                fb["repository_name"] = repository_name
            return fb

    if graph_id:
        result["repository_id"] = graph_id
    if repository_name:
        result["repository_name"] = repository_name
    return result
