import logging
from pathlib import Path
from typing import Dict, Any, List
from agents.base_agent import BaseAgent, AgentState

logger = logging.getLogger(__name__)


class HumanReviewAgent(BaseAgent):
    """Agent that identifies checkpoints requiring human input."""
    
    def __init__(self):
        super().__init__(
            name="human_review_agent",
            description="Identifies checkpoints requiring human input"
        )
    
    def execute(self, state: AgentState) -> AgentState:
        """Execute human review check."""
        logger.info("Human review agent checking for ambiguous cases")
        
        # Check for ambiguous dependencies
        dependencies = state.get("dependency_analysis", {}).get("dependencies", [])
        services = state.get("services", [])
        service_by_id = {str(service.get("id")): service for service in services}
        known_names = {
            str(value).strip().lower()
            for service in services
            for value in (service.get("name"), service.get("module_name"))
            if str(value or "").strip()
        }
        ambiguous_deps = []
        
        for dep in dependencies:
            target = str(dep.get("target", "") or "").strip()
            if not target:
                continue

            normalized = target.lower()
            if normalized in known_names:
                continue
            if any(normalized.startswith(f"{name}.") for name in known_names):
                continue

            source_service = service_by_id.get(str(dep.get("source") or ""))
            source_name = (
                str(source_service.get("module_name") or source_service.get("name") or dep.get("source") or "").strip()
                if source_service
                else str(dep.get("source") or "").strip()
            )
            original = str(dep.get("original_target") or target)
            candidates = [
                str(service.get("module_name") or service.get("name") or "").strip()
                for service in services
                if str(service.get("module_name") or service.get("name") or "").strip()
                and (
                    normalized in str(service.get("module_name") or service.get("name") or "").strip().lower()
                    or str(service.get("module_name") or service.get("name") or "").strip().lower() in normalized
                )
            ][:5]
            file_path = str(dep.get("file") or "")
            ambiguous_deps.append(
                {
                    "source_service_id": dep.get("source"),
                    "source_service_name": source_name,
                    "source_path": str(source_service.get("path") or "") if source_service else "",
                    "import_target": original,
                    "normalized_target": target,
                    "dependency_type": dep.get("type", "unknown"),
                    "file": file_path,
                    "file_name": Path(file_path).name if file_path else "",
                    "possible_matches": candidates,
                    "explanation": (
                        f"`{source_name}` imports `{original}`, but the analyzer could not confidently map it "
                        "to a known module/service in this repository."
                    ),
                }
            )
        
        # Check for unclear service boundaries
        unclear_services = []
        
        for service in services:
            if not service.get("language") or service.get("language") == "unknown":
                unclear_services.append(service)
        
        # Create checkpoints if needed
        if ambiguous_deps:
            self.should_request_human_review(
                state,
                reason="ambiguous_dependencies",
                question=f"Found {len(ambiguous_deps)} ambiguous dependencies. Please clarify:",
                options=["Ignore", "Map manually", "Review each"],
                context={
                    "summary": f"{len(ambiguous_deps)} dependencies could not be mapped with confidence.",
                    "ambiguous_dependencies": ambiguous_deps[:25],
                    "service_count": len(services),
                },
            )
        
        if unclear_services:
            self.should_request_human_review(
                state,
                reason="unclear_service_boundaries",
                question=f"Found {len(unclear_services)} services with unclear boundaries. Please review:",
                options=["Auto-detect", "Manual review", "Skip"]
            )
        
        state.add_history({
            "agent": self.name,
            "action": "checked_for_review",
            "ambiguous_dependencies": len(ambiguous_deps),
            "unclear_services": len(unclear_services),
        })
        
        logger.info(f"Human review agent completed: {len(ambiguous_deps)} ambiguous deps, {len(unclear_services)} unclear services")
        return state
