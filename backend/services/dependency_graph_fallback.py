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
        classification_counts: Dict[str, int] = {}
        nodes: List[Dict[str, Any]] = []
        for r in rows:
            metadata = r.meta_data or {}
            classification = str(metadata.get("classification") or "unknown")
            classification_counts[classification] = classification_counts.get(classification, 0) + 1
            nodes.append(
                {
                    "id": r.id,
                    "name": r.name,
                    "language": r.language or "",
                    "metadata": metadata,
                    "classification": classification,
                    "entry_point_count": int(metadata.get("entry_point_count") or 0),
                }
            )
        return {
            "nodes": nodes,
            "edges": [],
            "indirect_edges": [],
            "architecture_summary": {
                "service_count": len(nodes),
                "direct_edge_count": 0,
                "indirect_edge_count": 0,
                "isolated_count": len(nodes),
                "isolated_node_ids": [node["id"] for node in nodes[:8]],
                "entry_point_service_count": sum(1 for node in nodes if int(node.get("entry_point_count") or 0) > 0),
                "classification_counts": classification_counts,
                "most_depends_on": [],
                "most_depended_on": [],
                "cycle_count": 0,
            },
            "graph_source": "postgres_services",
            "graph_note": "Services loaded from the database. Neo4j had no nodes or no dependency edges for this repository — run analysis with Neo4j for full DEPENDS_ON relationships.",
        }
    except Exception:
        logger.exception("Postgres graph fallback failed for %s", repository_id)
        return None
    finally:
        db.close()
