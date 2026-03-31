"""Persist tech-debt analyzer output to Postgres (reports + items)."""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List

from core.database import SessionLocal
from models.tech_debt import TechDebtItem, TechDebtReport

logger = logging.getLogger(__name__)


def _empty_analysis() -> Dict[str, Any]:
    return {
        "total_debt_score": 0.0,
        "debt_density": 0.0,
        "total_items": 0,
        "category_scores": {
            "code_quality": 0.0,
            "architecture": 0.0,
            "dependency": 0.0,
            "documentation": 0.0,
            "test_coverage": 0.0,
        },
        "items_by_category": {},
        "items_by_severity": {},
        "score_explanation": {},
        "debt_items": [],
    }


def save_tech_debt_report(
    repository_id: str,
    analysis_result: Dict[str, Any] | None,
    *,
    source: str = "pipeline",
) -> None:
    """
    Insert a TechDebtReport and related TechDebtItem rows for ``repository_id``.

    Used by the multi-agent pipeline (after ``tech_debt_agent``) and by
    ``POST /api/tech-debt/analyze``.
    """
    if not analysis_result:
        analysis_result = _empty_analysis()

    scores = analysis_result.get("category_scores") or {}
    debt_items: List[Dict[str, Any]] = list(analysis_result.get("debt_items") or [])

    report_id = str(uuid.uuid4())
    db = SessionLocal()
    try:
        report = TechDebtReport(
            id=report_id,
            repository_id=repository_id,
            total_debt_score=analysis_result.get("total_debt_score", 0.0),
            debt_density=analysis_result.get("debt_density", 0.0),
            code_quality_score=scores.get("code_quality", 0.0),
            architecture_score=scores.get("architecture", 0.0),
            dependency_score=scores.get("dependency", 0.0),
            documentation_score=scores.get("documentation", 0.0),
            test_coverage_score=scores.get("test_coverage", scores.get("test", 0.0)),
            total_items=analysis_result.get("total_items", len(debt_items)),
            items_by_category=analysis_result.get("items_by_category") or {},
            items_by_severity=analysis_result.get("items_by_severity") or {},
            report_data={
                "generated_at": datetime.utcnow().isoformat(),
                "source": source,
                "assessment_coverage": analysis_result.get("assessment_coverage") or {},
                "score_explanation": analysis_result.get("score_explanation") or {},
            },
        )
        db.add(report)

        for item in debt_items:
            tech_item = TechDebtItem(
                id=str(uuid.uuid4()),
                repository_id=repository_id,
                file_path=item.get("file_path"),
                category=item.get("category", "code_quality"),
                severity=item.get("severity", "low"),
                priority=item.get("priority", 3),
                title=item.get("title", "Unknown issue"),
                description=item.get("description"),
                code_snippet=item.get("code_snippet"),
                line_start=item.get("line_start"),
                line_end=item.get("line_end"),
                impact_score=item.get("impact_score"),
                effort_estimate=item.get("effort_estimate"),
                meta_data=item.get("meta_data") or item.get("metadata") or {},
                status=item.get("status", "open"),
            )
            db.add(tech_item)

        db.commit()
        logger.info(
            "Saved tech debt report %s for repository %s (%s items)",
            report_id,
            repository_id,
            len(debt_items),
        )
    except Exception as exc:
        logger.exception("Failed to save tech debt report for %s: %s", repository_id, exc)
        db.rollback()
    finally:
        db.close()
