import logging
from typing import Dict, Any, List, Optional
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

    def _resolve_target_service(
        self,
        target: str,
        services: List[Dict[str, Any]],
        source_id: Optional[str],
    ) -> Optional[str]:
        """Resolve an imported symbol/module to a target service id.

        Prefer the most specific non-self service name match and never create
        a self-loop dependency from a fuzzy substring hit.
        """
        normalized_target = str(target or "").strip().lower()
        if not normalized_target:
            return None

        candidates: List[tuple[int, str]] = []
        for service in services:
            service_id = service.get("id")
            service_name = str(service.get("name") or "").strip().lower()
            module_name = str(service.get("module_name") or "").strip().lower()
            if not service_id or not service_name:
                continue
            if source_id and service_id == source_id:
                continue
            candidate_names = [value for value in {service_name, module_name} if value]
            matched = False
            for candidate_name in candidate_names:
                if normalized_target == candidate_name:
                    candidates.append((1000 + len(candidate_name), service_id))
                    matched = True
                    break
                dotted_prefix = f"{candidate_name}."
                if normalized_target.startswith(dotted_prefix) or f".{candidate_name}." in normalized_target:
                    candidates.append((100 + len(candidate_name), service_id))
                    matched = True
                    break
                if normalized_target.startswith(candidate_name):
                    candidates.append((10 + len(candidate_name), service_id))
                    matched = True
                    break
                if candidate_name in normalized_target:
                    candidates.append((len(candidate_name), service_id))
                    matched = True
                    break
            if matched:
                continue

        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]
    
    def execute(self, state: AgentState) -> AgentState:
        """Execute dependency mapping."""
        repository_path = state.get("repository_path")
        repository_id = state.get("repository_id")
        
        if not repository_path:
            raise ValueError("repository_path not found in state")
        
        logger.info(f"Dependency mapper agent analyzing: {repository_path}")
        
        # Analyze repository dependencies
        analysis_result = self.dependency_analyzer.analyze_repository(repository_path)

        if repository_id:
            self.graph_service.clear_repository_graph(repository_id)
        
        # Store services in graph
        for service in analysis_result["services"]:
            self.graph_service.create_service_node(
                service_id=service["id"],
                name=service["name"],
                repository_id=repository_id or "unknown",
                language=service["language"],
                metadata={
                    "path": service["path"],
                    "module_name": service.get("module_name"),
                    "classification": service.get("classification"),
                    "entry_points": service.get("entry_points") or [],
                    "entry_point_count": service.get("entry_point_count") or 0,
                }
            )
        
        # Create dependency relationships
        for dep in analysis_result["dependencies"]:
            source_id = dep.get("source")
            target = dep.get("target")

            target_service = self._resolve_target_service(
                target=str(target or ""),
                services=analysis_result["services"],
                source_id=source_id,
            )

            if source_id and target_service and source_id != target_service:
                self.graph_service.create_dependency(
                    source_service_id=source_id,
                    target_service_id=target_service,
                    dependency_type=dep.get("type", "unknown"),
                    metadata={
                        "original": dep.get("original_target") or target,
                        "normalized_target": target,
                    }
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
        state.update("module_inventory", analysis_result.get("modules") or [])
        state.update("entry_points", analysis_result.get("entry_points") or [])
        
        state.add_history({
            "agent": self.name,
            "action": "mapped_dependencies",
            "services_found": len(analysis_result["services"]),
            "dependencies_found": len(analysis_result["dependencies"]),
            "entry_points_found": len(analysis_result.get("entry_points") or []),
        })
        
        logger.info(f"Dependency mapper agent completed: {len(analysis_result['services'])} services")
        return state
