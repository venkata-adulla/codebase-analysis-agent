from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from core.security import verify_api_key

router = APIRouter()


class ServiceResponse(BaseModel):
    service_id: str
    name: str
    repository_id: str
    language: str
    description: Optional[str] = None
    endpoints: List[dict] = []
    created_at: datetime


@router.get("/")
async def list_services(
    repository_id: Optional[str] = None,
    api_key: bool = Depends(verify_api_key)
):
    """List all services."""
    # TODO: Implement service listing
    return {"services": []}


@router.get("/{service_id}")
async def get_service(
    service_id: str,
    api_key: bool = Depends(verify_api_key)
):
    """Get service details."""
    # TODO: Implement service retrieval
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Service not found"
    )


@router.get("/{service_id}/dependencies")
async def get_service_dependencies(
    service_id: str,
    api_key: bool = Depends(verify_api_key)
):
    """Get service dependencies."""
    # TODO: Implement dependency retrieval
    return {
        "service_id": service_id,
        "dependencies": []
    }
