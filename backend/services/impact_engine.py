import logging
from typing import List, Dict, Any, Optional, Tuple

from services.graph_service import GraphService

logger = logging.getLogger(__name__)


class ImpactEngine:
    """Engine for analyzing change impact."""

    def __init__(self):
        self.graph_service = GraphService()

    def _load_services_for_repository(self, repository_id: str) -> List[Any]:
        from core.database import SessionLocal
        from models.service import Service as ServiceRow

        db = SessionLocal()
        try:
            return (
                db.query(ServiceRow)
                .filter(ServiceRow.repository_id == repository_id)
                .order_by(ServiceRow.name.asc())
                .all()
            )
        finally:
            db.close()

    def _heuristic_surface_impact(
        self,
        row: Any,
        desc_lower: str,
    ) -> Tuple[float, str, List[str]]:
        """Return (score, reason, what_could_break bullets) for a service without graph detail."""
        lang = (row.language or "unknown").lower()
        breaks: List[str] = []
        score = 0.25
        reason_parts: List[str] = []

        py_change = "python" in desc_lower and any(
            w in desc_lower for w in ("upgrade", "version", "bump", "runtime", "interpreter")
        )
        node_change = any(w in desc_lower for w in ("node", "npm", "pnpm", "yarn")) and any(
            w in desc_lower for w in ("upgrade", "version", "bump")
        )
        db_change = any(w in desc_lower for w in ("database", "schema", "migration", "postgres", "mysql"))
        breaking = any(w in desc_lower for w in ("breaking", "remove", "delete", "deprecate"))

        if py_change:
            if lang in ("python", "unknown", ""):
                score = 0.72 if breaking else 0.58
                reason_parts.append("Python runtime or dependency changes directly affect this service boundary.")
                breaks.extend(
                    [
                        "Pinned wheels / lockfiles may fail to resolve on the new interpreter",
                        "Removed stdlib or syntax changes can break runtime behavior",
                        "Docker/CI images and virtualenvs must be rebuilt to match",
                    ]
                )
            else:
                score = max(score, 0.2)
                reason_parts.append("Non-Python service — lower direct runtime risk unless shared tooling uses Python.")

        if node_change:
            if lang in ("javascript", "typescript", "unknown", ""):
                score = max(score, 0.65 if breaking else 0.52)
                reason_parts.append("Node/npm ecosystem upgrades affect build, tests, and bundlers for this service.")
                breaks.extend(
                    [
                        "Native addons may need rebuild (node-gyp)",
                        "Peer dependency conflicts after major bumps",
                        "Jest/ESLint/Next config may require migration",
                    ]
                )

        if db_change:
            score = min(0.85, score + 0.15)
            reason_parts.append("Database or schema work can break persistence and migrations across consumers.")
            breaks.extend(
                [
                    "Migration ordering and rollback plans",
                    "ORM/query compatibility with new schema",
                    "Backfill jobs and read replicas",
                ]
            )

        if breaking and score < 0.5:
            score = min(0.75, score + 0.2)
            reason_parts.append("Breaking-change wording suggests higher compatibility risk.")

        if not reason_parts:
            reason_parts.append(
                "Heuristic surface-area review: this service is part of the repository and may need regression testing."
            )
            breaks.extend(
                [
                    "Integration and contract tests for this boundary",
                    "Deployment and config drift (env vars, feature flags)",
                ]
            )

        return score, " ".join(reason_parts), breaks[:6]

    def analyze_impact(
        self,
        repository_id: str,
        change_description: str,
        affected_files: Optional[List[str]] = None,
        affected_services: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Analyze the impact of a change."""
        impacted_services: List[Dict[str, Any]] = []
        desc_lower = (change_description or "").lower()
        global_breaks: List[str] = []
        risk_summary = ""

        if affected_services:
            seen_ids = set()
            for service_id in affected_services:
                dependents = self.graph_service.find_impacted_services(service_id)
                for dependent in dependents:
                    sid = dependent["service_id"]
                    if sid in seen_ids:
                        continue
                    seen_ids.add(sid)
                    impacted_services.append(
                        {
                            "service_id": sid,
                            "service_name": dependent["name"],
                            "impact_score": self._calculate_impact_score(dependent["depth"], change_description),
                            "impact_type": "transitive",
                            "reason": f"Transitive dependent of {service_id}",
                            "depth": dependent["depth"],
                            "what_could_break": [
                                "Downstream API contracts may change",
                                "Cascading test failures in consumers",
                            ],
                        }
                    )
            if impacted_services:
                risk_summary = (
                    f"Transitive downstream impact from the selected service(s): {len(impacted_services)} "
                    "node(s) in the Neo4j graph."
                )

        elif affected_files:
            pass
        else:
            rows = self._load_services_for_repository(repository_id)
            if not rows:
                risk_summary = (
                    "No services are stored for this repository yet. Run a full repository analysis so "
                    "services are persisted; then re-run impact analysis for a meaningful blast-radius view."
                )
                global_breaks.append("Cannot estimate per-service impact until services exist in the inventory.")
            else:
                risk_summary = (
                    f"Scoring {len(rows)} service(s) in this repository against your change description "
                    "(heuristic; augment with Neo4j dependency graph when available)."
                )
                if "python" in desc_lower:
                    global_breaks.append(
                        "Verify requirements.txt / pyproject.toml / Poetry lock compatibility with the target runtime."
                    )
                if any(w in desc_lower for w in ("docker", "image", "container")):
                    global_breaks.append("Rebuild and scan container images; check base image tags and libc compatibility.")

                for row in rows:
                    score, reason, breaks = self._heuristic_surface_impact(row, desc_lower)
                    impacted_services.append(
                        {
                            "service_id": row.id,
                            "service_name": row.name,
                            "impact_score": round(min(score, 1.0), 3),
                            "impact_type": "repository_surface",
                            "reason": reason,
                            "what_could_break": breaks,
                        }
                    )

            try:
                g = self.graph_service.get_dependency_graph(repository_id)
                edge_count = len(g.get("edges") or [])
                node_count = len(g.get("nodes") or [])
                if node_count and edge_count:
                    risk_summary += (
                        f" Graph overlay: {node_count} node(s), {edge_count} edge(s) — "
                        "use the Dependency graph page for transitive relationships."
                    )
            except Exception:
                logger.debug("Neo4j graph unavailable for impact summary", exc_info=True)

        risk_level = self._calculate_risk_level(impacted_services)
        recommendations = self._generate_recommendations(impacted_services, risk_level, desc_lower)

        return {
            "change_description": change_description,
            "impacted_services": impacted_services,
            "risk_level": risk_level,
            "recommendations": recommendations,
            "total_impacted": len(impacted_services),
            "risk_summary": risk_summary,
            "global_what_could_break": global_breaks[:8],
        }
    
    def _calculate_impact_score(
        self,
        depth: int,
        change_description: str
    ) -> float:
        """Calculate impact score (0-1)."""
        # Deeper dependencies have lower impact scores
        base_score = 1.0 / (depth + 1)
        
        # Adjust based on change description keywords
        high_impact_keywords = ["breaking", "remove", "delete", "deprecate"]
        low_impact_keywords = ["add", "enhance", "optimize"]
        
        description_lower = change_description.lower()
        
        if any(keyword in description_lower for keyword in high_impact_keywords):
            base_score *= 1.5
        elif any(keyword in description_lower for keyword in low_impact_keywords):
            base_score *= 0.7
        
        return min(base_score, 1.0)
    
    def _calculate_risk_level(self, impacted_services: List[Dict[str, Any]]) -> str:
        """Calculate overall risk level."""
        if not impacted_services:
            return "low"

        max_score = max(s["impact_score"] for s in impacted_services)
        high = sum(1 for s in impacted_services if s["impact_score"] >= 0.65)
        n = len(impacted_services)

        if max_score >= 0.8 or high >= 4:
            return "critical"
        if max_score >= 0.55 or high >= 2 or n >= 8:
            return "high"
        if max_score >= 0.35 or high >= 1 or n >= 3:
            return "medium"
        return "low"

    def _generate_recommendations(
        self,
        impacted_services: List[Dict[str, Any]],
        risk_level: str,
        desc_lower: str = "",
    ) -> List[str]:
        """Generate recommendations based on impact analysis."""
        recommendations: List[str] = []

        if risk_level == "critical":
            recommendations.append("Treat as high-risk release: feature-freeze, staged rollout, and rollback plan.")
            recommendations.append("Run full regression, contract tests, and canary deploy before 100% traffic.")
        elif risk_level == "high":
            recommendations.append("Expand test matrix (unit, integration, e2e) for every listed service.")
            recommendations.append("Review dependency lockfiles and deployment manifests together.")
        elif risk_level == "medium":
            recommendations.append("Schedule focused QA on the highest-scoring services first.")
        else:
            recommendations.append("Smaller blast radius — still run CI and smoke tests before promote.")

        if "python" in desc_lower:
            recommendations.append("Validate `pip check` / Poetry or uv lock resolution on the target Python version.")
        if any(w in desc_lower for w in ("database", "schema", "migration")):
            recommendations.append("Plan migration order, backups, and backward-compatible reads during cutover.")

        if len(impacted_services) > 10:
            recommendations.append(
                f"Many services flagged ({len(impacted_services)}); consider splitting the change or automating checks."
            )

        return recommendations[:12]
