import logging
from typing import Dict, Any
from agents.base_agent import BaseAgent, AgentState
from services.impact_engine import ImpactEngine

logger = logging.getLogger(__name__)


class ImpactAgent(BaseAgent):
    """Agent that performs change impact analysis and risk assessment."""
    
    def __init__(self):
        super().__init__(
            name="impact_agent",
            description="Performs change impact analysis and risk assessment"
        )
        self.impact_engine = ImpactEngine()
    
    def execute(self, state: AgentState) -> AgentState:
        """Execute impact analysis preparation."""
        repository_id = state.get("repository_id")
        
        if not repository_id:
            logger.warning("No repository_id found, skipping impact analysis")
            return state
        
        logger.info("Impact agent preparing impact analysis capabilities")
        
        # Get dependency graph
        graph = self.impact_engine.graph_service.get_dependency_graph(repository_id)
        
        state.update("dependency_graph", graph)
        state.update("impact_analysis_ready", True)
        
        state.add_history({
            "agent": self.name,
            "action": "prepared_impact_analysis",
            "services_in_graph": len(graph.get("nodes", [])),
            "dependencies_in_graph": len(graph.get("edges", [])),
        })
        
        logger.info("Impact agent completed: impact analysis ready")
        return state
