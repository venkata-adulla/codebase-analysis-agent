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
        metadata = row.meta_data or {}
        classification = str(metadata.get("classification") or "unknown").replace("_", " ")
        entry_point_count = int(metadata.get("entry_point_count") or 0)
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

        if classification in {"entrypoint", "package root"} or entry_point_count > 0:
            score = min(0.92, score + 0.12)
            reason_parts.append("This module looks like an entry surface, so user-facing blast radius is higher.")
            breaks.append("CLI/app startup behavior and packaging entry points may regress")

        if classification in {"core library", "application module"}:
            score = min(0.9, score + 0.08)
            reason_parts.append("Core library code tends to fan out into more downstream callers.")

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

    def _match_services_from_files(self, rows: List[Any], affected_files: List[str]) -> List[Any]:
        normalized_files = [str(path or "").replace("\\", "/").lower() for path in affected_files if str(path or "").strip()]
        matched: List[Any] = []
        seen = set()

        for row in rows:
            service_path = str(getattr(row, "file_path", "") or "").replace("\\", "/").lower().rstrip("/")
            if not service_path:
                continue
            for changed in normalized_files:
                candidate = changed.lower().rstrip("/")
                if candidate.startswith(service_path) or service_path.endswith(candidate):
                    if row.id not in seen:
                        matched.append(row)
                        seen.add(row.id)
                    break
        return matched

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
        rows = self._load_services_for_repository(repository_id)
        row_by_id = {row.id: row for row in rows}
        graph_summary: Dict[str, Any] = {}

        try:
            graph_summary = self.graph_service.get_dependency_graph(repository_id)
        except Exception:
            logger.debug("Neo4j graph unavailable for impact summary", exc_info=True)

        def append_impacted(item: Dict[str, Any]):
            existing = next((entry for entry in impacted_services if entry["service_id"] == item["service_id"]), None)
            if existing:
                existing["impact_score"] = max(existing["impact_score"], item["impact_score"])
                existing["what_could_break"] = list(
                    dict.fromkeys([*(existing.get("what_could_break") or []), *(item.get("what_could_break") or [])])
                )[:8]
                if len(str(item.get("reason") or "")) > len(str(existing.get("reason") or "")):
                    existing["reason"] = item["reason"]
                if item.get("depth") is not None:
                    existing["depth"] = min(existing.get("depth", item["depth"]), item["depth"])
                return
            impacted_services.append(item)

        if affected_services:
            for service_id in affected_services:
                row = row_by_id.get(service_id)
                append_impacted(
                    {
                        "service_id": service_id,
                        "service_name": getattr(row, "name", service_id),
                        "impact_score": 0.92,
                        "impact_type": "direct_selection",
                        "reason": "Explicitly selected as directly changed.",
                        "depth": 0,
                        "what_could_break": [
                            "This module is part of the proposed code change",
                            "Behavior, contracts, or packaging may change at the source",
                        ],
                    }
                )
                dependents = self.graph_service.find_impacted_services(service_id)
                for dependent in dependents:
                    sid = dependent["service_id"]
                    append_impacted(
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
            if not rows:
                risk_summary = "No services are stored for this repository yet, so changed files could not be mapped."
            else:
                directly_changed = self._match_services_from_files(rows, affected_files)
                if directly_changed:
                    for row in directly_changed:
                        score, reason, breaks = self._heuristic_surface_impact(row, desc_lower)
                        append_impacted(
                            {
                                "service_id": row.id,
                                "service_name": row.name,
                                "impact_score": round(min(score + 0.18, 1.0), 3),
                                "impact_type": "direct_file_match",
                                "reason": f"Changed file maps into this module. {reason}",
                                "depth": 0,
                                "classification": (row.meta_data or {}).get("classification"),
                                "what_could_break": list(
                                    dict.fromkeys(
                                        ["Changed files live under this module path", *breaks]
                                    )
                                )[:8],
                            }
                        )
                        for dependent in self.graph_service.find_impacted_services(row.id):
                            append_impacted(
                                {
                                    "service_id": dependent["service_id"],
                                    "service_name": dependent["name"],
                                    "impact_score": self._calculate_impact_score(dependent["depth"], change_description),
                                    "impact_type": "transitive",
                                    "reason": f"Depends on changed module {row.name}.",
                                    "depth": dependent["depth"],
                                    "what_could_break": [
                                        "Downstream callers may depend on changed behavior",
                                        "Integration tests and internal contracts may fail",
                                    ],
                                }
                            )
                    risk_summary = (
                        f"Matched {len(directly_changed)} directly changed module(s) from file paths and expanded to "
                        f"{len(impacted_services)} impacted node(s) including transitive dependents."
                    )
                else:
                    risk_summary = (
                        "No stored service paths matched the changed files. Falling back to repository-wide heuristics."
                    )
        else:
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

        edge_count = len(graph_summary.get("edges") or [])
        indirect_edge_count = len(graph_summary.get("indirect_edges") or [])
        node_count = len(graph_summary.get("nodes") or [])
        architecture = graph_summary.get("architecture_summary") or {}
        if node_count:
            risk_summary += (
                f" Graph overlay: {node_count} node(s), {edge_count} direct edge(s), {indirect_edge_count} indirect edge(s)."
            )
            if architecture.get("entry_point_service_count"):
                global_breaks.append(
                    f"{architecture['entry_point_service_count']} entry-point module(s) detected; verify CLI/app startup behavior."
                )
            if architecture.get("cycle_count"):
                global_breaks.append(
                    f"Dependency graph contains {architecture['cycle_count']} cycle(s); regression paths may be harder to isolate."
                )

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
            "graph_summary": architecture,
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
