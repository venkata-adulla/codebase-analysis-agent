import hashlib
import logging
import re
from typing import List, Dict, Any, Optional, Set
from pathlib import Path
from services.code_parser import CodeParserService
from services.repository_manager import RepositoryManager

logger = logging.getLogger(__name__)


class DependencyAnalyzer:
    """Analyzes dependencies between services and components."""
    
    def __init__(self):
        self.parser_service = CodeParserService()
        self.repo_manager = RepositoryManager()
    
    def analyze_repository(
        self,
        repository_path: str
    ) -> Dict[str, Any]:
        """Analyze dependencies in a repository."""
        results = {
            "services": [],
            "dependencies": [],
            "api_endpoints": [],
            "databases": [],
            "message_queues": [],
        }
        
        # Identify services (directories with main files, package.json, etc.)
        services = self._identify_services(repository_path)
        results["services"] = services
        
        # Analyze dependencies for each service
        for service in services:
            service_deps = self._analyze_service_dependencies(
                service["path"],
                service["id"]
            )
            results["dependencies"].extend(service_deps["dependencies"])
            results["api_endpoints"].extend(service_deps["api_endpoints"])
            results["databases"].extend(service_deps["databases"])
            results["message_queues"].extend(service_deps["message_queues"])
        
        return results
    
    def _identify_services(
        self,
        repository_path: str
    ) -> List[Dict[str, Any]]:
        """Identify services in a repository."""
        services = []
        path = Path(repository_path)
        
        # Look for service indicators
        service_indicators = [
            "main.py",
            "app.py",
            "server.py",
            "package.json",
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "requirements.txt",
            "Pipfile",
            "go.mod",
            "Cargo.toml",
            "pom.xml",
            "build.gradle",
            "Dockerfile",
            "docker-compose.yml",
        ]
        ignore_dirs = {".git", "node_modules", ".venv", "venv", "__pycache__", ".next", "dist", "build"}
        
        # Find directories with service indicators
        import os
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]
            root_path = Path(root)
            if any(indicator in files for indicator in service_indicators):
                service_name = root_path.name
                service_id = self._build_service_id(service_name, root_path)
                
                # Determine language
                language = self._detect_language(root_path)
                
                services.append({
                    "id": service_id,
                    "name": service_name,
                    "path": str(root_path),
                    "language": language,
                })

        # Heuristic fallback: if we only detected the repo root, split into meaningful code clusters.
        if len(services) <= 1:
            existing_paths = {str(Path(s["path"]).resolve()) for s in services}
            discovered = self._discover_code_clusters(path, existing_paths)
            if discovered:
                only_root_detected = len(services) == 1 and str(Path(services[0]["path"]).resolve()) == str(path.resolve())
                if only_root_detected:
                    services = discovered
                else:
                    services.extend(discovered)
        
        # If no services found, treat root as a single service
        if not services:
            services.append({
                "id": self._build_service_id("root_service", path),
                "name": Path(repository_path).name,
                "path": repository_path,
                "language": "unknown",
            })
        
        return services

    def _build_service_id(self, service_name: str, service_path: Path) -> str:
        """Build a stable service id (Python's hash() is process-randomized)."""
        stable_hash = hashlib.sha1(str(service_path.resolve()).encode("utf-8")).hexdigest()[:12]
        safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", service_name).strip("_") or "service"
        return f"{safe_name}_{stable_hash}"

    def _discover_code_clusters(self, repository_root: Path, existing_paths: Set[str]) -> List[Dict[str, Any]]:
        """Discover likely service folders from top-level and src/* code-heavy directories."""
        discovered: List[Dict[str, Any]] = []
        ignore_names = {
            ".git", ".github", ".vscode", "__pycache__", "node_modules", ".venv", "venv", "dist", "build",
            "docs", "doc", "examples", "example", "scripts", "tests", "test",
        }
        code_exts = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs"}

        candidate_dirs: List[Path] = []
        for child in repository_root.iterdir():
            if child.is_dir() and child.name not in ignore_names and not child.name.startswith("."):
                candidate_dirs.append(child)

        src_dir = repository_root / "src"
        if src_dir.exists() and src_dir.is_dir():
            for child in src_dir.iterdir():
                if child.is_dir() and child.name not in ignore_names and not child.name.startswith("."):
                    candidate_dirs.append(child)

        seen: Set[str] = set()
        for candidate in candidate_dirs:
            resolved = str(candidate.resolve())
            if resolved in seen or resolved in existing_paths:
                continue
            seen.add(resolved)

            code_file_count = 0
            for ext in code_exts:
                code_file_count += sum(1 for _ in candidate.rglob(f"*{ext}"))
                if code_file_count >= 3:
                    break

            if code_file_count < 3:
                continue

            name = candidate.name
            discovered.append(
                {
                    "id": self._build_service_id(name, candidate),
                    "name": name,
                    "path": str(candidate),
                    "language": self._detect_language(candidate),
                }
            )

        return discovered
    
    def _detect_language(self, path: Path) -> str:
        """Detect the primary language of a service."""
        files = list(path.rglob("*"))
        
        extensions = {}
        for file in files:
            if file.is_file():
                ext = file.suffix
                extensions[ext] = extensions.get(ext, 0) + 1
        
        if extensions.get(".py", 0) > 0:
            return "python"
        elif extensions.get(".js", 0) > 0 or extensions.get(".ts", 0) > 0:
            return "javascript"
        elif extensions.get(".java", 0) > 0:
            return "java"
        else:
            return "unknown"
    
    def _analyze_service_dependencies(
        self,
        service_path: str,
        service_id: str
    ) -> Dict[str, Any]:
        """Analyze dependencies for a single service."""
        dependencies = []
        api_endpoints = []
        databases = []
        message_queues = []
        
        path = Path(service_path)
        
        # Get all code files
        code_files = []
        for ext in [".py", ".js", ".jsx", ".ts", ".tsx", ".java"]:
            code_files.extend(path.rglob(f"*{ext}"))
        
        for file_path in code_files:
            if not file_path.is_file():
                continue
            
            file_str = str(file_path)
            
            # Extract imports/dependencies
            deps = self.parser_service.extract_dependencies(file_str)
            
            for dep in deps.get("third_party", []) + deps.get("local", []):
                dependencies.append({
                    "source": service_id,
                    "target": dep,
                    "type": "import",
                    "file": file_str,
                })
            
            # Detect API calls
            api_calls = self._detect_api_calls(file_str)
            api_endpoints.extend(api_calls)
            
            # Detect database connections
            db_connections = self._detect_database_connections(file_str)
            databases.extend(db_connections)
            
            # Detect message queues
            mq_connections = self._detect_message_queues(file_str)
            message_queues.extend(mq_connections)
        
        return {
            "dependencies": dependencies,
            "api_endpoints": api_endpoints,
            "databases": databases,
            "message_queues": message_queues,
        }
    
    def _detect_api_calls(self, file_path: str) -> List[Dict[str, Any]]:
        """Detect API calls in a file."""
        api_calls = []
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # HTTP client patterns
            patterns = [
                (r"requests\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]", "python"),
                (r"fetch\s*\(\s*['\"]([^'\"]+)['\"]", "javascript"),
                (r"axios\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]", "javascript"),
                (r"http\.(get|post|put|delete)\s*\([^,]+,\s*['\"]([^'\"]+)['\"]", "java"),
            ]
            
            for pattern, lang in patterns:
                for match in re.finditer(pattern, content):
                    method = match.group(1) if len(match.groups()) > 1 else "get"
                    url = match.group(2) if len(match.groups()) > 1 else match.group(1)
                    
                    api_calls.append({
                        "endpoint": url,
                        "method": method.upper(),
                        "file": file_path,
                        "language": lang,
                    })
        
        except Exception as e:
            logger.error(f"Error detecting API calls in {file_path}: {e}")
        
        return api_calls
    
    def _detect_database_connections(self, file_path: str) -> List[Dict[str, Any]]:
        """Detect database connections in a file."""
        databases = []
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Database connection patterns
            patterns = [
                (r"psycopg2\.connect|sqlite3\.connect|mysql\.connector", "sql"),
                (r"pymongo\.MongoClient|motor\.MotorClient", "mongodb"),
                (r"redis\.Redis|redis\.StrictRedis", "redis"),
                (r"neo4j\.GraphDatabase\.driver", "neo4j"),
                (r"Connection|DataSource", "java"),
            ]
            
            for pattern, db_type in patterns:
                if re.search(pattern, content):
                    databases.append({
                        "type": db_type,
                        "file": file_path,
                    })
        
        except Exception as e:
            logger.error(f"Error detecting database connections in {file_path}: {e}")
        
        return databases
    
    def _detect_message_queues(self, file_path: str) -> List[Dict[str, Any]]:
        """Detect message queue connections in a file."""
        message_queues = []
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Message queue patterns
            patterns = [
                (r"pika\.BlockingConnection|pika\.SelectConnection", "rabbitmq"),
                (r"kafka\.KafkaProducer|kafka\.KafkaConsumer", "kafka"),
                (r"boto3\.client\s*\(\s*['\"]sqs['\"]", "sqs"),
                (r"@RabbitListener|@KafkaListener", "java"),
            ]
            
            for pattern, mq_type in patterns:
                if re.search(pattern, content):
                    message_queues.append({
                        "type": mq_type,
                        "file": file_path,
                    })
        
        except Exception as e:
            logger.error(f"Error detecting message queues in {file_path}: {e}")
        
        return message_queues
    
    def map_service_dependencies(
        self,
        dependencies: List[Dict[str, Any]],
        services: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Map dependencies to actual services."""
        service_map = {s["id"]: s for s in services}
        mapped_deps = []
        
        for dep in dependencies:
            target = dep["target"]
            
            # Try to find matching service
            matched_service = None
            for service in services:
                if target.startswith(service["name"]) or service["name"] in target:
                    matched_service = service["id"]
                    break
            
            if matched_service:
                mapped_deps.append({
                    "source": dep["source"],
                    "target": matched_service,
                    "type": "service_dependency",
                    "original": target,
                })
        
        return mapped_deps
