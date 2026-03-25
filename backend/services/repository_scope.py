"""Resolve user-supplied repo tokens to canonical repository UUIDs for filtering."""

from typing import Optional

from sqlalchemy.orm import Session

from models.repository import Repository
from models.service import Service as ServiceRow


def resolve_repository_id(db: Session, token: Optional[str]) -> Optional[str]:
    """
    Map a URL/query token to the repository UUID used on services and Neo4j.

    Accepts:
    - Repository primary key (analysis ``repository_id``)
    - Service primary key (e.g. ``root_service``)
    - Service ``name`` when it was set to a folder UUID or other unique string
    - Substrings of ``services.file_path`` or ``repositories.local_path`` (clone folder names)
    """
    if not token:
        return None
    t = token.strip()
    if not t:
        return None

    if db.query(Repository).filter(Repository.id == t).first():
        return t

    if db.query(ServiceRow).filter(ServiceRow.repository_id == t).first():
        return t

    svc = db.query(ServiceRow).filter(ServiceRow.id == t).first()
    if svc:
        return svc.repository_id

    svc = db.query(ServiceRow).filter(ServiceRow.name == t).first()
    if svc:
        return svc.repository_id

    like = f"%{t}%"
    svc = db.query(ServiceRow).filter(ServiceRow.file_path.isnot(None), ServiceRow.file_path.like(like)).first()
    if svc:
        return svc.repository_id

    repo = db.query(Repository).filter(Repository.local_path.isnot(None), Repository.local_path.like(like)).first()
    if repo:
        return repo.id

    return None
