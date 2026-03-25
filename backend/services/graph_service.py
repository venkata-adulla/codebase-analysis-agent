import json
import logging
from collections import Counter, defaultdict, deque
from typing import List, Dict, Any, Optional, Set, Tuple
from core.database import get_neo4j_driver

logger = logging.getLogger(__name__)


def _serialize_metadata(meta: Optional[Dict[str, Any]]) -> str:
    """Neo4j properties cannot be dicts; serialize to JSON string."""
    if not meta:
        return "{}"
    return json.dumps(meta, default=str)


def _deserialize_metadata(meta: Any) -> Dict[str, Any]:
    if not meta:
        return {}
    if isinstance(meta, dict):
        return meta
    if isinstance(meta, str):
        try:
            parsed = json.loads(meta)
            return parsed if isinstance(parsed, dict) else {"raw": meta}
        except Exception:
            return {"raw": meta}
    return {"raw": str(meta)}


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
            result = session.run(
                query,
                service_id=service_id,
                name=name,
                repository_id=repository_id,
                language=language,
                metadata=_serialize_metadata(metadata),
            )
            result.consume()
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
            result = session.run(
                query,
                file_id=file_id,
                file_path=file_path,
                service_id=service_id,
                metadata=_serialize_metadata(metadata),
            )
            result.consume()
    
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
            result = session.run(
                query,
                function_id=function_id,
                function_name=function_name,
                file_id=file_id,
                metadata=_serialize_metadata(metadata),
            )
            result.consume()
    
    def create_dependency(
        self,
        source_service_id: str,
        target_service_id: str,
        dependency_type: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Create a dependency relationship between services."""
        if not source_service_id or not target_service_id:
            logger.warning("Skipping dependency with empty endpoint: %s -> %s", source_service_id, target_service_id)
            return
        if source_service_id == target_service_id:
            logger.info("Skipping self-loop dependency: %s -> %s", source_service_id, target_service_id)
            return
        with self.driver.session() as session:
            query = """
            MATCH (source:Service {id: $source_service_id})
            MATCH (target:Service {id: $target_service_id})
            MERGE (source)-[r:DEPENDS_ON {type: $dependency_type}]->(target)
            SET r.metadata = $metadata,
                r.created_at = datetime()
            RETURN r
            """
            result = session.run(
                query,
                source_service_id=source_service_id,
                target_service_id=target_service_id,
                dependency_type=dependency_type,
                metadata=_serialize_metadata(metadata),
            )
            result.consume()
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
            result = session.run(
                query,
                service_id=service_id,
                api_endpoint=api_endpoint,
                method=method,
                metadata=_serialize_metadata(metadata),
            )
            result.consume()
    
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
            result = session.run(
                query,
                service_id=service_id,
                database_name=database_name,
                connection_type=connection_type,
                metadata=_serialize_metadata(metadata),
            )
            result.consume()
    
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
            rows = [record.data() for record in result]
            for row in rows:
                row["metadata"] = _deserialize_metadata(row.get("metadata"))
            return rows

    def _compute_indirect_edges(
        self,
        nodes: List[Dict[str, Any]],
        direct_edges: List[Dict[str, Any]],
        max_depth: int = 4,
    ) -> List[Dict[str, Any]]:
        adjacency: Dict[str, Set[str]] = defaultdict(set)
        direct_pairs = {(edge["source"], edge["target"]) for edge in direct_edges if edge.get("source") and edge.get("target")}
        node_ids = {node["id"] for node in nodes if node.get("id")}

        for edge in direct_edges:
            source = edge.get("source")
            target = edge.get("target")
            if source and target and source != target:
                adjacency[source].add(target)

        indirect_edges: List[Dict[str, Any]] = []
        seen_pairs: Set[Tuple[str, str]] = set()
        for source in node_ids:
            queue = deque([(source, [source])])
            while queue:
                current, path = queue.popleft()
                if len(path) > max_depth:
                    continue
                for neighbor in adjacency.get(current, set()):
                    if neighbor in path:
                        continue
                    next_path = [*path, neighbor]
                    if len(next_path) >= 3 and (source, neighbor) not in direct_pairs and (source, neighbor) not in seen_pairs:
                        indirect_edges.append(
                            {
                                "source": source,
                                "target": neighbor,
                                "type": "indirect",
                                "depth": len(next_path) - 1,
                                "metadata": {
                                    "kind": "indirect",
                                    "via": next_path[1:-1],
                                    "path": next_path,
                                },
                            }
                        )
                        seen_pairs.add((source, neighbor))
                    queue.append((neighbor, next_path))

        return indirect_edges

    def _compute_cycle_count(self, edges: List[Dict[str, Any]]) -> int:
        adjacency: Dict[str, Set[str]] = defaultdict(set)
        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            if source and target and source != target:
                adjacency[source].add(target)

        cycles: Set[Tuple[str, ...]] = set()

        def dfs(node: str, start: str, path: List[str]):
            for neighbor in adjacency.get(node, set()):
                if neighbor == start and len(path) > 1:
                    cycle = tuple(sorted(path))
                    cycles.add(cycle)
                    continue
                if neighbor in path or len(path) >= 6:
                    continue
                dfs(neighbor, start, [*path, neighbor])

        for start in adjacency:
            dfs(start, start, [start])

        return len(cycles)

    def _build_architecture_summary(
        self,
        nodes: List[Dict[str, Any]],
        direct_edges: List[Dict[str, Any]],
        indirect_edges: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        incoming = Counter()
        outgoing = Counter()
        classification_counts = Counter()
        isolated: List[str] = []
        entry_point_nodes = 0

        linked_ids = set()
        for edge in direct_edges:
            if edge.get("source"):
                outgoing[edge["source"]] += 1
                linked_ids.add(edge["source"])
            if edge.get("target"):
                incoming[edge["target"]] += 1
                linked_ids.add(edge["target"])

        for node in nodes:
            metadata = node.get("metadata") or {}
            classification = str(node.get("classification") or metadata.get("classification") or "unknown")
            classification_counts[classification] += 1
            if int(metadata.get("entry_point_count") or 0) > 0:
                entry_point_nodes += 1
            if node.get("id") and node["id"] not in linked_ids:
                isolated.append(node["id"])

        most_outgoing = outgoing.most_common(3)
        most_incoming = incoming.most_common(3)
        return {
            "service_count": len(nodes),
            "direct_edge_count": len(direct_edges),
            "indirect_edge_count": len(indirect_edges),
            "isolated_count": len(isolated),
            "isolated_node_ids": isolated[:8],
            "entry_point_service_count": entry_point_nodes,
            "classification_counts": dict(classification_counts),
            "most_depends_on": [
                {"service_id": service_id, "count": count}
                for service_id, count in most_outgoing
            ],
            "most_depended_on": [
                {"service_id": service_id, "count": count}
                for service_id, count in most_incoming
            ],
            "cycle_count": self._compute_cycle_count(direct_edges),
        }
    
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
            for edge in edges:
                edge["metadata"] = _deserialize_metadata(edge.get("metadata"))
                edge.setdefault("kind", "direct")
            
            # Get all service nodes
            if repository_id:
                node_query = """
                MATCH (s:Service {repository_id: $repository_id})
                RETURN s.id as id, s.name as name, s.language as language, s.metadata as metadata
                """
                node_result = session.run(node_query, repository_id=repository_id)
            else:
                node_query = """
                MATCH (s:Service)
                RETURN s.id as id, s.name as name, s.language as language, s.metadata as metadata
                """
                node_result = session.run(node_query)
            
            nodes = [record.data() for record in node_result]
            for node in nodes:
                node["metadata"] = _deserialize_metadata(node.get("metadata"))
                node["classification"] = node["metadata"].get("classification")
                node["entry_point_count"] = int(node["metadata"].get("entry_point_count") or 0)

            indirect_edges = self._compute_indirect_edges(nodes, edges)
            architecture_summary = self._build_architecture_summary(nodes, edges, indirect_edges)
            
            return {
                "nodes": nodes,
                "edges": edges,
                "indirect_edges": indirect_edges,
                "architecture_summary": architecture_summary,
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
            impacted = [record.data() for record in result]
            for item in impacted:
                item["impact_kind"] = "transitive"
            return impacted
    
    def clear_repository_graph(self, repository_id: str):
        """Clear all graph data for a repository."""
        with self.driver.session() as session:
            query = """
            MATCH (s:Service {repository_id: $repository_id})
            DETACH DELETE s
            """
            result = session.run(query, repository_id=repository_id)
            result.consume()
            logger.info(f"Cleared graph for repository: {repository_id}")
