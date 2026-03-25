"""Persist discovered services (and doc snippets) from orchestrator state to Postgres."""

import logging
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from core.database import SessionLocal
from models.service import Service as ServiceRow

logger = logging.getLogger(__name__)


def persist_services_and_docs(
    repository_id: str,
    services: List[Dict[str, Any]],
    documentation: Dict[str, Any],
) -> None:
    """Upsert services from dependency mapper state; merge LLM doc text into description."""
    if not services and not documentation:
        return

    db: Session = SessionLocal()
    try:
        incoming_services = services or []
        incoming_ids = {
            str(s.get("id") or "").strip()
            for s in incoming_services
            if str(s.get("id") or "").strip()
        }
        if incoming_ids:
            # Keep repository inventory in sync across reruns; drop stale rows.
            db.query(ServiceRow).filter(
                ServiceRow.repository_id == repository_id,
                ~ServiceRow.id.in_(incoming_ids),
            ).delete(synchronize_session=False)

        for s in services or []:
            sid = str(s.get("id") or "").strip()
            if not sid:
                continue
            name = (s.get("name") or "unnamed").strip() or "unnamed"
            row = db.query(ServiceRow).filter(ServiceRow.id == sid).first()
            desc = s.get("description")
            doc_blob = documentation.get(sid) if isinstance(documentation, dict) else None
            if isinstance(doc_blob, dict):
                doc_text = doc_blob.get("description")
                if isinstance(doc_text, str) and doc_text.strip():
                    desc = doc_text.strip()[:10000]

            if row:
                row.name = name
                row.repository_id = repository_id
                row.language = s.get("language")
                row.file_path = s.get("path")
                if desc is not None:
                    row.description = desc
            else:
                db.add(
                    ServiceRow(
                        id=sid,
                        repository_id=repository_id,
                        name=name,
                        language=s.get("language"),
                        description=desc,
                        file_path=s.get("path"),
                        meta_data=None,
                    )
                )

        if isinstance(documentation, dict):
            for sid, doc_blob in documentation.items():
                if not isinstance(doc_blob, dict):
                    continue
                text = doc_blob.get("description")
                if not isinstance(text, str) or not text.strip():
                    continue
                row = db.query(ServiceRow).filter(ServiceRow.id == str(sid)).first()
                if row and (not row.description or not str(row.description).strip()):
                    row.description = text.strip()[:10000]

        db.commit()
        logger.info("Persisted services for repository %s", repository_id)
    except Exception:
        logger.exception("Failed to persist services for %s", repository_id)
        db.rollback()
    finally:
        db.close()
