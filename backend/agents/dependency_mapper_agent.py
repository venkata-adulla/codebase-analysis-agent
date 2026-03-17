import logging
from typing import Dict, Any
from agents.base_agent import BaseAgent, AgentState
from services.dependency_analyzer import DependencyAnalyzer
from services.graph_service import GraphService

logger = logging.getLogger(__name__)


class DependencyMapperAgent(BaseAgent):
    """Agent that builds dependency graphs and identifies relationships."""
    
    def __init__(self):
        super().__init__(
            name="dependency_mapper_agent",
            description="Builds dependency graphs and identifies relationships"
        )
        self.dependency_analyzer = DependencyAnalyzer()
        self.graph_service = GraphService()
    
    def execute(self, state: AgentState) -> AgentState:
        """Execute dependency mapping."""
        repository_path = state.get("repository_path")
        repository_id = state.get("repository_id")
        
        if not repository_path:
            raise ValueError("repository_path not found in state")
        
        logger.info(f"Dependency mapper agent analyzing: {repository_path}")
        
        # Analyze repository dependencies
        analysis_result = self.dependency_analyzer.analyze_repository(repository_path)
        
        # Store services in graph
        for service in analysis_result["services"]:
            self.graph_service.create_service_node(
                service_id=service["id"],
                name=service["name"],
                repository_id=repository_id or "unknown",
                language=service["language"],
                metadata={"path": service["path"]}
            )
        
        # Create dependency relationships
        service_map = {s["id"]: s for s in analysis_result["services"]}
        
        for dep in analysis_result["dependencies"]:
            source_id = dep.get("source")
            target = dep.get("target")
            
            # Try to find target service
            target_service = None
            for service in analysis_result["services"]:
                if target.startswith(service["name"]) or service["name"] in target:
                    target_service = service["id"]
                    break
            
            if source_id and target_service:
                self.graph_service.create_dependency(
                    source_service_id=source_id,
                    target_service_id=target_service,
                    dependency_type=dep.get("type", "unknown"),
                    metadata={"original": target}
                )
        
        # Store API endpoints
        for api in analysis_result["api_endpoints"]:
            # Find service for this API call
            for service in analysis_result["services"]:
                if api["file"].startswith(service["path"]):
                    self.graph_service.create_api_call(
                        service_id=service["id"],
                        api_endpoint=api["endpoint"],
                        method=api["method"],
                        metadata={"file": api["file"]}
                    )
                    break
        
        # Store database connections
        for db in analysis_result["databases"]:
            for service in analysis_result["services"]:
                if db["file"].startswith(service["path"]):
                    self.graph_service.create_database_connection(
                        service_id=service["id"],
                        database_name="unknown",
                        connection_type=db["type"],
                        metadata={"file": db["file"]}
                    )
                    break
        
        state.update("dependency_analysis", analysis_result)
        state.update("services", analysis_result["services"])
        
        state.add_history({
            "agent": self.name,
            "action": "mapped_dependencies",
            "services_found": len(analysis_result["services"]),
            "dependencies_found": len(analysis_result["dependencies"]),
        })
        
        logger.info(f"Dependency mapper agent completed: {len(analysis_result['services'])} services")
        return state
