from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Dict, Any
from core.security import verify_api_key

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
    repository_id: str = None,
    api_key: bool = Depends(verify_api_key)
):
    """Get full dependency graph."""
    from services.graph_service import GraphService
    
    graph_service = GraphService()
    graph = graph_service.get_dependency_graph(repository_id)
    
    return graph
