from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional, Any, Dict
from sqlalchemy.orm import Session

from core.security import verify_api_key
from core.database import SessionLocal
from models.repository import Repository
from models.service import Service as ServiceRow
from services.repository_scope import resolve_repository_id

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/")
async def list_services(
    repository_id: Optional[str] = Query(None),
    api_key: bool = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """List services discovered during analysis (Postgres).

    ``repository_id`` may be the analysis repository UUID, a service id, a service name,
    or a clone-folder / path fragment (see ``resolve_repository_id``).
    """
    q = db.query(ServiceRow, Repository.name.label("repository_name")).outerjoin(
        Repository, Repository.id == ServiceRow.repository_id
    )
    if repository_id:
        resolved = resolve_repository_id(db, repository_id)
        if resolved:
            q = q.filter(ServiceRow.repository_id == resolved)
        else:
            q = q.filter(ServiceRow.repository_id == repository_id)
    rows = q.order_by(ServiceRow.repository_id.desc(), ServiceRow.name.asc()).all()
    return {
        "services": [
            {
                "id": row.id,
                "name": row.name,
                "repository_id": row.repository_id,
                "repository_name": repository_name,
                "language": row.language or "",
                "classification": (row.meta_data or {}).get("classification"),
                "entry_point_count": int((row.meta_data or {}).get("entry_point_count") or 0),
                "description": row.description,
                "path": row.file_path,
                "meta_data": row.meta_data,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row, repository_name in rows
        ]
    }


@router.get("/{service_id}/dependencies")
async def get_service_dependencies(
    service_id: str,
    api_key: bool = Depends(verify_api_key),
):
    """Get service dependencies from the graph store."""
    from services.graph_service import GraphService

    graph_service = GraphService()
    deps = graph_service.get_service_dependencies(service_id)
    return {
        "service_id": service_id,
        "dependencies": deps,
    }


@router.get("/{service_id}")
async def get_service(
    service_id: str,
    api_key: bool = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """Get a single service with optional documentation metadata."""
    row = db.query(ServiceRow).filter(ServiceRow.id == service_id).first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found",
        )
    payload: Dict[str, Any] = {
        "id": row.id,
        "name": row.name,
        "repository_id": row.repository_id,
        "repository_name": (
            db.query(Repository.name).filter(Repository.id == row.repository_id).scalar()
        ),
        "language": row.language or "",
        "description": row.description,
        "path": row.file_path,
        "meta_data": row.meta_data,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    return payload
