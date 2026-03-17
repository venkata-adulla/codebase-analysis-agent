import logging
from typing import List, Dict, Any, Optional
from core.database import get_neo4j_driver

logger = logging.getLogger(__name__)


class GraphService:
    """Service for managing Neo4j graph database operations."""
    
    def __init__(self):
        self.driver = get_neo4j_driver()
    
    def create_service_node(
        self,
        service_id: str,
        name: str,
        repository_id: str,
        language: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Create a service node in the graph."""
        with self.driver.session() as session:
            query = """
            MERGE (s:Service {id: $service_id})
            SET s.name = $name,
                s.repository_id = $repository_id,
                s.language = $language,
                s.metadata = $metadata
            RETURN s
            """
            session.run(
                query,
                service_id=service_id,
                name=name,
                repository_id=repository_id,
                language=language,
                metadata=metadata or {}
            )
            logger.info(f"Created service node: {service_id}")
    
    def create_file_node(
        self,
        file_id: str,
        file_path: str,
        service_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Create a file node and link it to a service."""
        with self.driver.session() as session:
            query = """
            MATCH (s:Service {id: $service_id})
            MERGE (f:File {id: $file_id})
            SET f.path = $file_path,
                f.metadata = $metadata
            MERGE (f)-[:BELONGS_TO]->(s)
            RETURN f
            """
            session.run(
                query,
                file_id=file_id,
                file_path=file_path,
                service_id=service_id,
                metadata=metadata or {}
            )
    
    def create_function_node(
        self,
        function_id: str,
        function_name: str,
        file_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Create a function node and link it to a file."""
        with self.driver.session() as session:
            query = """
            MATCH (f:File {id: $file_id})
            MERGE (func:Function {id: $function_id})
            SET func.name = $function_name,
                func.metadata = $metadata
            MERGE (func)-[:DEFINED_IN]->(f)
            RETURN func
            """
            session.run(
                query,
                function_id=function_id,
                function_name=function_name,
                file_id=file_id,
                metadata=metadata or {}
            )
    
    def create_dependency(
        self,
        source_service_id: str,
        target_service_id: str,
        dependency_type: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Create a dependency relationship between services."""
        with self.driver.session() as session:
            query = """
            MATCH (source:Service {id: $source_service_id})
            MATCH (target:Service {id: $target_service_id})
            MERGE (source)-[r:DEPENDS_ON {type: $dependency_type}]->(target)
            SET r.metadata = $metadata,
                r.created_at = datetime()
            RETURN r
            """
            session.run(
                query,
                source_service_id=source_service_id,
                target_service_id=target_service_id,
                dependency_type=dependency_type,
                metadata=metadata or {}
            )
            logger.info(f"Created dependency: {source_service_id} -> {target_service_id}")
    
    def create_api_call(
        self,
        service_id: str,
        api_endpoint: str,
        method: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Create an API endpoint node and link it to a service."""
        with self.driver.session() as session:
            query = """
            MATCH (s:Service {id: $service_id})
            MERGE (api:APIEndpoint {endpoint: $api_endpoint})
            SET api.method = $method,
                api.metadata = $metadata
            MERGE (s)-[:CALLS_API]->(api)
            RETURN api
            """
            session.run(
                query,
                service_id=service_id,
                api_endpoint=api_endpoint,
                method=method,
                metadata=metadata or {}
            )
    
    def create_database_connection(
        self,
        service_id: str,
        database_name: str,
        connection_type: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Create a database node and link it to a service."""
        with self.driver.session() as session:
            query = """
            MATCH (s:Service {id: $service_id})
            MERGE (db:Database {name: $database_name})
            SET db.type = $connection_type,
                db.metadata = $metadata
            MERGE (s)-[:USES_DB]->(db)
            RETURN db
            """
            session.run(
                query,
                service_id=service_id,
                database_name=database_name,
                connection_type=connection_type,
                metadata=metadata or {}
            )
    
    def get_service_dependencies(
        self,
        service_id: str
    ) -> List[Dict[str, Any]]:
        """Get all dependencies for a service."""
        with self.driver.session() as session:
            query = """
            MATCH (s:Service {id: $service_id})-[r:DEPENDS_ON]->(target:Service)
            RETURN target.id as service_id,
                   target.name as name,
                   target.language as language,
                   r.type as dependency_type,
                   r.metadata as metadata
            """
            result = session.run(query, service_id=service_id)
            return [record.data() for record in result]
    
    def get_dependency_graph(
        self,
        repository_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get the full dependency graph."""
        with self.driver.session() as session:
            if repository_id:
                query = """
                MATCH (s1:Service {repository_id: $repository_id})-[r:DEPENDS_ON]->(s2:Service)
                RETURN s1.id as source,
                       s2.id as target,
                       r.type as type,
                       r.metadata as metadata
                """
                result = session.run(query, repository_id=repository_id)
            else:
                query = """
                MATCH (s1:Service)-[r:DEPENDS_ON]->(s2:Service)
                RETURN s1.id as source,
                       s2.id as target,
                       r.type as type,
                       r.metadata as metadata
                """
                result = session.run(query)
            
            edges = [record.data() for record in result]
            
            # Get all service nodes
            if repository_id:
                node_query = """
                MATCH (s:Service {repository_id: $repository_id})
                RETURN s.id as id, s.name as name, s.language as language
                """
                node_result = session.run(node_query, repository_id=repository_id)
            else:
                node_query = """
                MATCH (s:Service)
                RETURN s.id as id, s.name as name, s.language as language
                """
                node_result = session.run(node_query)
            
            nodes = [record.data() for record in node_result]
            
            return {
                "nodes": nodes,
                "edges": edges,
            }
    
    def find_impacted_services(
        self,
        service_id: str,
        max_depth: int = 5
    ) -> List[Dict[str, Any]]:
        """Find all services that depend on the given service (transitive)."""
        with self.driver.session() as session:
            query = """
            MATCH path = (target:Service {id: $service_id})<-[*1..$max_depth]-(dependent:Service)
            RETURN DISTINCT dependent.id as service_id,
                   dependent.name as name,
                   length(path) as depth
            ORDER BY depth
            """
            result = session.run(query, service_id=service_id, max_depth=max_depth)
            return [record.data() for record in result]
    
    def clear_repository_graph(self, repository_id: str):
        """Clear all graph data for a repository."""
        with self.driver.session() as session:
            query = """
            MATCH (s:Service {repository_id: $repository_id})
            DETACH DELETE s
            """
            session.run(query, repository_id=repository_id)
            logger.info(f"Cleared graph for repository: {repository_id}")
