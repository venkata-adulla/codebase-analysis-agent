"""Persist discovered services (and doc snippets) from orchestrator state to Postgres."""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from core.database import SessionLocal
from models.service import Service as ServiceRow
from services.service_description import build_service_description, is_stub_description as _is_stub_description

logger = logging.getLogger(__name__)


def _lookup_documentation_blob(
    documentation: Any, service_id: str
) -> Optional[Dict[str, Any]]:
    """Match documentation entry by service id (keys may be str or other hashables)."""
    if not isinstance(documentation, dict):
        return None
    key = str(service_id or "").strip()
    blob = documentation.get(key)
    if isinstance(blob, dict):
        return blob
    for k, v in documentation.items():
        if str(k).strip() == key and isinstance(v, dict):
            return v
    return None


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
            metadata = {
                "module_name": s.get("module_name"),
                "classification": s.get("classification"),
                "entry_points": s.get("entry_points") or [],
                "entry_point_count": s.get("entry_point_count") or 0,
            }
            row = db.query(ServiceRow).filter(ServiceRow.id == sid).first()
            desc = s.get("description")
            doc_blob = _lookup_documentation_blob(documentation, sid)
            summary_from_doc: Optional[str] = None
            if isinstance(doc_blob, dict):
                doc_text = doc_blob.get("description")
                if isinstance(doc_text, str) and doc_text.strip() and not _is_stub_description(doc_text):
                    desc = doc_text.strip()[:10000]
                sum_text = doc_blob.get("summary")
                if isinstance(sum_text, str) and sum_text.strip():
                    summary_from_doc = sum_text.strip()[:4000]
                    logger.info(
                        "Persisting service %s summary_len=%d",
                        sid,
                        len(summary_from_doc),
                    )
            # Replace empty or bare-stub descriptions with a structured fallback
            if _is_stub_description(desc):
                desc = build_service_description(
                    service_name=name,
                    language=s.get("language"),
                    metadata=metadata,
                    path=s.get("path"),
                )

            if row:
                row.name = name
                row.repository_id = repository_id
                row.language = s.get("language")
                row.file_path = s.get("path")
                row.meta_data = metadata
                if desc is not None:
                    row.description = desc
                if summary_from_doc is not None:
                    row.summary = summary_from_doc
            else:
                db.add(
                    ServiceRow(
                        id=sid,
                        repository_id=repository_id,
                        name=name,
                        language=s.get("language"),
                        description=desc,
                        summary=summary_from_doc,
                        file_path=s.get("path"),
                        meta_data=metadata,
                    )
                )

        if isinstance(documentation, dict):
            for sid, doc_blob in documentation.items():
                if not isinstance(doc_blob, dict):
                    continue
                text = doc_blob.get("description")
                if _is_stub_description(text):
                    continue
                row = db.query(ServiceRow).filter(ServiceRow.id == str(sid)).first()
                if row and _is_stub_description(row.description):
                    row.description = (text or "").strip()[:10000]
                sum_text = doc_blob.get("summary")
                if (
                    row
                    and isinstance(sum_text, str)
                    and sum_text.strip()
                    and not (row.summary or "").strip()
                ):
                    row.summary = sum_text.strip()[:4000]
                    logger.info(
                        "Backfilled summary for service %s summary_len=%d",
                        sid,
                        len(row.summary or ""),
                    )

        # Safety net: replace any stub descriptions that slipped through
        for row in db.query(ServiceRow).filter(ServiceRow.repository_id == repository_id).all():
            if not _is_stub_description(row.description):
                continue
            row.description = build_service_description(
                service_name=str(row.name or "Service"),
                language=row.language,
                metadata=row.meta_data or {},
                path=row.file_path,
            )

        db.commit()
        logger.info("Persisted services for repository %s", repository_id)
    except Exception:
        logger.exception("Failed to persist services for %s", repository_id)
        db.rollback()
    finally:
        db.close()
