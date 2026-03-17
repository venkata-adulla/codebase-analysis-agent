import logging
from typing import Dict, Any
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
        ambiguous_deps = []
        
        for dep in dependencies:
            target = dep.get("target", "")
            # If target doesn't match a known service, it's ambiguous
            services = state.get("services", [])
            service_names = [s["name"] for s in services]
            
            if not any(name in target for name in service_names):
                ambiguous_deps.append(dep)
        
        # Check for unclear service boundaries
        services = state.get("services", [])
        unclear_services = []
        
        for service in services:
            if not service.get("language") or service.get("language") == "unknown":
                unclear_services.append(service)
        
        # Create checkpoints if needed
        if ambiguous_deps:
            state.should_request_human_review(
                state,
                reason="ambiguous_dependencies",
                question=f"Found {len(ambiguous_deps)} ambiguous dependencies. Please clarify:",
                options=["Ignore", "Map manually", "Review each"]
            )
        
        if unclear_services:
            state.should_request_human_review(
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
