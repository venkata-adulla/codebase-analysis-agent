"""When Neo4j has no nodes or is unavailable, build a minimal graph from Postgres services."""

import logging
from typing import Any, Dict, List, Optional

from core.database import SessionLocal
from models.service import Service as ServiceRow

logger = logging.getLogger(__name__)


def graph_from_postgres_services(repository_id: str) -> Optional[Dict[str, Any]]:
    """Return service rows as graph nodes (no edges) so the UI can still visualize inventory."""
    db = SessionLocal()
    try:
        rows = (
            db.query(ServiceRow)
            .filter(ServiceRow.repository_id == repository_id)
            .order_by(ServiceRow.name.asc())
            .all()
        )
        if not rows:
            return None
        nodes: List[Dict[str, Any]] = [
            {"id": r.id, "name": r.name, "language": r.language or ""} for r in rows
        ]
        return {
            "nodes": nodes,
            "edges": [],
            "graph_source": "postgres_services",
            "graph_note": "Services loaded from the database. Neo4j had no nodes or no dependency edges for this repository — run analysis with Neo4j for full DEPENDS_ON relationships.",
        }
    except Exception:
        logger.exception("Postgres graph fallback failed for %s", repository_id)
        return None
    finally:
        db.close()
