import hashlib
import logging
import os
import re
import sys
from collections import Counter
from typing import List, Dict, Any, Optional, Set, Tuple
from pathlib import Path
from services.code_parser import CodeParserService
from services.repository_manager import RepositoryManager

logger = logging.getLogger(__name__)
STDLIB_MODULES = set(getattr(sys, "stdlib_module_names", ())) | {
    "argparse", "ast", "collections", "csv", "datetime", "functools", "hashlib",
    "inspect", "itertools", "json", "logging", "math", "os", "pathlib", "re",
    "subprocess", "sys", "typing", "unittest", "urllib",
}


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
        path = Path(repository_path)
        results = {
            "services": [],
            "modules": [],
            "dependencies": [],
            "api_endpoints": [],
            "databases": [],
            "message_queues": [],
            "entry_points": [],
            "classification_summary": {},
        }
        
        # Identify services (directories with main files, package.json, etc.)
        services = self._identify_services(repository_path)
        if self._should_use_java_package_modules(path, services):
            java_modules = self._identify_java_package_services(path)
            if java_modules and len(java_modules) >= 2:
                services = java_modules
        elif self._should_use_python_modules(path, services):
            python_modules = self._identify_python_module_services(path)
            if python_modules:
                services = python_modules
        results["services"] = services
        results["entry_points"] = [
            {**entry, "service_id": service["id"], "service_name": service["name"]}
            for service in services
            for entry in (service.get("entry_points") or [])
        ]
        results["modules"] = self._build_module_inventory(Path(repository_path), services)
        results["classification_summary"] = dict(
            Counter(
                str(item.get("classification") or "unknown")
                for item in [*services, *results["modules"]]
            )
        )
        
        # Analyze dependencies for each service
        for service in services:
            service_deps = self._analyze_service_dependencies(
                service,
                path,
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
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]
            root_path = Path(root)
            if any(indicator in files for indicator in service_indicators):
                service_name = root_path.name
                service_id = self._build_service_id(service_name, root_path)
                
                # Determine language
                language = self._detect_language(root_path)
                entry_points = self._detect_entry_points(root_path, language, path)
                classification = self._classify_module(root_path, path, language, files, entry_points)
                
                services.append({
                    "id": service_id,
                    "name": service_name,
                    "path": str(root_path),
                    "language": language,
                    "classification": classification,
                    "entry_points": entry_points,
                    "entry_point_count": len(entry_points),
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

    def _has_maven_or_gradle(self, repository_root: Path) -> bool:
        return (
            (repository_root / "pom.xml").is_file()
            or (repository_root / "build.gradle").is_file()
            or (repository_root / "build.gradle.kts").is_file()
            or (repository_root / "settings.gradle.kts").is_file()
        )

    def _find_java_source_roots(self, repository_root: Path) -> List[Path]:
        """Production Java sources only (not src/test/java)."""
        p = repository_root / "src" / "main" / "java"
        return [p] if p.is_dir() else []

    def _java_cluster_subdirs(self, java_root: Path, max_clusters: int = 64) -> List[Path]:
        """
        Descend past single-package chains (org/com/...) until a directory has multiple
        subpackages that each contain .java files — typical Maven/Gradle layout.
        """
        cur = java_root
        for _ in range(24):
            children = [
                c
                for c in cur.iterdir()
                if c.is_dir() and not c.name.startswith(".")
            ]
            has_java_here = any(cur.glob("*.java"))
            if has_java_here:
                break
            if len(children) == 1:
                cur = children[0]
                continue
            if len(children) >= 2:
                with_java = [c for c in children if any(c.rglob("*.java"))]
                if len(with_java) >= 2:
                    return sorted(with_java, key=lambda p: p.name.lower())[:max_clusters]
                if len(with_java) == 1:
                    cur = with_java[0]
                    continue
                if len(children) == 1:
                    cur = children[0]
                    continue
            break

        children = [c for c in cur.iterdir() if c.is_dir() and not c.name.startswith(".")]
        with_java = [c for c in children if any(c.rglob("*.java"))]
        if len(with_java) >= 2:
            return sorted(with_java, key=lambda p: p.name.lower())[:max_clusters]
        if any(java_root.rglob("*.java")):
            return [java_root]
        return []

    def _classify_java_cluster(self, cluster_dir: Path, repository_root: Path) -> str:
        rel = str(cluster_dir.resolve().relative_to(repository_root.resolve())).lower()
        parts = rel.replace("\\", "/").split("/")
        if any(p in {"tests", "test"} for p in parts):
            return "test"
        if any(p in {"examples", "example"} for p in parts):
            return "example"
        if any(p in {"docs", "doc"} for p in parts):
            return "documentation"
        if "controller" in rel or "rest" in rel or "web" in rel:
            return "entrypoint"
        return "core_library"

    def _detect_java_entry_points(self, cluster_dir: Path, repository_root: Path) -> List[Dict[str, Any]]:
        entry_points: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        for fp in cluster_dir.rglob("*.java"):
            if not fp.is_file():
                continue
            try:
                text = fp.read_text(encoding="utf-8", errors="ignore")[:24_000]
            except Exception:
                continue
            if re.search(r"public\s+static\s+void\s+main\s*\(", text):
                rel = str(fp.resolve().relative_to(repository_root.resolve()))
                key = f"java_main:{rel}"
                if key not in seen:
                    entry_points.append({"type": "java_main", "file": rel})
                    seen.add(key)
        return entry_points

    def _identify_java_package_services(self, repository_root: Path) -> List[Dict[str, Any]]:
        services: List[Dict[str, Any]] = []
        for java_root in self._find_java_source_roots(repository_root):
            clusters = self._java_cluster_subdirs(java_root)
            for cluster_dir in clusters:
                if not any(cluster_dir.rglob("*.java")):
                    continue
                try:
                    rel = cluster_dir.relative_to(java_root)
                except ValueError:
                    continue
                module_name = ".".join(rel.parts) if rel.parts else java_root.name
                name = rel.parts[-1] if rel.parts else module_name
                entry_points = self._detect_java_entry_points(cluster_dir, repository_root)
                services.append(
                    {
                        "id": self._build_service_id(module_name.replace(".", "_"), cluster_dir),
                        "name": name,
                        "module_name": module_name,
                        "path": str(cluster_dir),
                        "language": "java",
                        "classification": self._classify_java_cluster(cluster_dir, repository_root),
                        "entry_points": entry_points,
                        "entry_point_count": len(entry_points),
                    }
                )
        return services

    def _should_use_java_package_modules(
        self,
        repository_root: Path,
        services: List[Dict[str, Any]],
    ) -> bool:
        if not self._has_maven_or_gradle(repository_root):
            return False
        roots = self._find_java_source_roots(repository_root)
        if not roots:
            return False
        clusters = self._java_cluster_subdirs(roots[0])
        if len(clusters) < 2:
            return False
        java_count = sum(1 for _ in (repository_root / "src" / "main" / "java").rglob("*.java")) if (repository_root / "src" / "main" / "java").is_dir() else 0
        if java_count < 4:
            return False
        # Prefer packages when current detection is coarse (repo root, src/, main/, or few clusters)
        coarse = len(services) <= 3
        names = {str(s.get("name") or "").lower() for s in services}
        looks_maven_layout = bool(names & {"src", "main", "java"}) or len(services) <= 2
        return coarse or looks_maven_layout

    def _should_use_python_modules(
        self,
        repository_root: Path,
        services: List[Dict[str, Any]],
    ) -> bool:
        pyproject = repository_root / "pyproject.toml"
        setup_py = repository_root / "setup.py"
        src_dir = repository_root / "src"
        python_files = list(repository_root.rglob("*.py"))
        if len(python_files) < 5:
            return False
        has_python_package = any((child / "__init__.py").exists() for child in src_dir.iterdir()) if src_dir.exists() else False
        if not has_python_package:
            has_python_package = any(
                child.is_dir() and (child / "__init__.py").exists()
                for child in repository_root.iterdir()
                if child.is_dir() and child.name not in {"tests", "test", "docs", "examples", "example"}
            )
        # Prefer module-level view for library repos or when current detection is still coarse.
        return bool(has_python_package and (pyproject.exists() or setup_py.exists() or len(services) <= 12))

    def _candidate_python_package_roots(self, repository_root: Path) -> List[Path]:
        candidates: List[Path] = []
        seen: Set[str] = set()

        def add_if_package(path: Path):
            resolved = str(path.resolve())
            if resolved in seen:
                return
            if path.is_dir() and (path / "__init__.py").exists():
                seen.add(resolved)
                candidates.append(path)

        src_dir = repository_root / "src"
        if src_dir.exists() and src_dir.is_dir():
            for child in src_dir.iterdir():
                if child.name.startswith(".") or child.name in {"tests", "test", "docs", "examples", "example"}:
                    continue
                add_if_package(child)

        for child in repository_root.iterdir():
            if child.name.startswith(".") or child.name in {"src", "tests", "test", "docs", "examples", "example"}:
                continue
            add_if_package(child)

        return candidates

    def _module_name_for_file(self, file_path: Path, package_root: Path) -> str:
        rel = file_path.relative_to(package_root)
        parts = [package_root.name]
        suffixless = rel.with_suffix("")
        parts.extend(list(suffixless.parts))
        if parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts)

    def _classify_python_module_file(self, file_path: Path, repository_root: Path) -> str:
        rel_parts = [part.lower() for part in file_path.relative_to(repository_root).parts]
        name = file_path.name.lower()
        if any(part in {"tests", "test"} for part in rel_parts) or name.startswith("test_"):
            return "test"
        if any(part in {"examples", "example"} for part in rel_parts):
            return "example"
        if any(part in {"docs", "doc"} for part in rel_parts):
            return "documentation"
        if name == "__main__.py" or name in {"cli.py", "main.py"}:
            return "entrypoint"
        if name == "__init__.py":
            return "package_root"
        if "src" in rel_parts:
            return "core_library"
        return "application_module"

    def _detect_entry_points_for_file(self, file_path: Path, repository_root: Path) -> List[Dict[str, Any]]:
        entry_points: List[Dict[str, Any]] = []
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return entry_points

        rel = str(file_path.resolve().relative_to(repository_root.resolve()))
        name = file_path.name.lower()
        if name == "__main__.py":
            entry_points.append({"type": "python_main", "file": rel})
        if name in {"main.py", "cli.py"} and (
            "__name__ == '__main__'" in text or '__name__ == "__main__"' in text
        ):
            entry_points.append({"type": "main_guard", "file": rel})
        if any(part in {"bin", "scripts"} for part in file_path.parts):
            entry_points.append({"type": "script_file", "file": rel})
        return entry_points

    def _identify_python_module_services(self, repository_root: Path) -> List[Dict[str, Any]]:
        services: List[Dict[str, Any]] = []
        package_roots = self._candidate_python_package_roots(repository_root)
        ignore_dirs = {"__pycache__", ".git", ".venv", "venv", "node_modules", "dist", "build"}

        for package_root in package_roots:
            python_files = sorted(
                [
                    path for path in package_root.rglob("*.py")
                    if path.is_file() and not any(part in ignore_dirs for part in path.parts)
                ],
                key=lambda path: (len(path.parts), str(path)),
            )
            if len(python_files) < 2:
                continue

            for file_path in python_files:
                module_name = self._module_name_for_file(file_path, package_root)
                if not module_name:
                    continue
                entry_points = self._detect_entry_points_for_file(file_path, repository_root)
                classification = self._classify_python_module_file(file_path, repository_root)
                services.append(
                    {
                        "id": self._build_service_id(module_name.replace(".", "_"), file_path),
                        "name": module_name,
                        "module_name": module_name,
                        "path": str(file_path),
                        "language": "python",
                        "classification": classification,
                        "entry_points": entry_points,
                        "entry_point_count": len(entry_points),
                    }
                )

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
            language = self._detect_language(candidate)
            entry_points = self._detect_entry_points(candidate, language, repository_root)
            discovered.append(
                {
                    "id": self._build_service_id(name, candidate),
                    "name": name,
                    "path": str(candidate),
                    "language": language,
                    "classification": self._classify_module(candidate, repository_root, language, None, entry_points),
                    "entry_points": entry_points,
                    "entry_point_count": len(entry_points),
                }
            )

        return discovered

    def _classify_module(
        self,
        module_path: Path,
        repository_root: Path,
        language: str,
        files: Optional[List[str]] = None,
        entry_points: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        rel = module_path.resolve().relative_to(repository_root.resolve())
        parts = [p.lower() for p in rel.parts]
        file_set = {f.lower() for f in (files or [])}
        ep_count = len(entry_points or [])

        if rel == Path("."):
            return "repository_root"
        if any(p in {"tests", "test"} for p in parts):
            return "test"
        if any(p in {"examples", "example"} for p in parts):
            return "example"
        if any(p in {"docs", "doc"} for p in parts):
            return "documentation"
        if ep_count > 0 or any(f in {"main.py", "__main__.py", "cli.py", "app.py", "server.py"} for f in file_set):
            return "entrypoint"
        if module_path.parent == repository_root / "src" or "src" in parts:
            return "core_library"
        if any(f in {"pyproject.toml", "setup.py", "setup.cfg", "package.json"} for f in file_set):
            return "package_root"
        if language in {"python", "javascript", "java"}:
            return "application_module"
        return "support_module"

    def _detect_entry_points(
        self,
        module_path: Path,
        language: str,
        repository_root: Path,
    ) -> List[Dict[str, Any]]:
        entry_points: List[Dict[str, Any]] = []
        candidate_files: List[Path] = []

        for name in ("__main__.py", "main.py", "cli.py", "app.py", "server.py", "pyproject.toml", "setup.py", "package.json"):
            fp = module_path / name
            if fp.exists() and fp.is_file():
                candidate_files.append(fp)

        seen: Set[str] = set()
        for file_path in candidate_files:
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            rel = str(file_path.resolve().relative_to(repository_root.resolve()))

            if file_path.name == "__main__.py":
                key = f"python_main:{rel}"
                if key not in seen:
                    entry_points.append({"type": "python_main", "file": rel})
                    seen.add(key)

            if "__name__ == '__main__'" in text or '__name__ == "__main__"' in text:
                key = f"main_guard:{rel}"
                if key not in seen:
                    entry_points.append({"type": "main_guard", "file": rel})
                    seen.add(key)

            if file_path.name == "pyproject.toml":
                if re.search(r"(?m)^\[project\.scripts\]", text) or re.search(r"(?m)^\[project\.entry-points\.", text):
                    key = f"python_console_scripts:{rel}"
                    if key not in seen:
                        entry_points.append({"type": "python_console_scripts", "file": rel})
                        seen.add(key)

            if file_path.name == "setup.py":
                if "console_scripts" in text or "entry_points" in text:
                    key = f"setup_console_scripts:{rel}"
                    if key not in seen:
                        entry_points.append({"type": "setup_console_scripts", "file": rel})
                        seen.add(key)

            if file_path.name == "package.json":
                if re.search(r'"bin"\s*:', text):
                    key = f"node_bin:{rel}"
                    if key not in seen:
                        entry_points.append({"type": "node_bin", "file": rel})
                        seen.add(key)
                if re.search(r'"start"\s*:', text):
                    key = f"node_start_script:{rel}"
                    if key not in seen:
                        entry_points.append({"type": "node_start_script", "file": rel})
                        seen.add(key)

        return entry_points

    def _build_module_inventory(self, repository_root: Path, services: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        modules: List[Dict[str, Any]] = []
        seen_paths: Set[str] = set()
        service_paths = {str(Path(s["path"]).resolve()) for s in services}

        candidates: List[Path] = [repository_root]
        for child in repository_root.iterdir():
            if child.name.startswith("."):
                continue
            if child.is_dir():
                candidates.append(child)

        src_dir = repository_root / "src"
        if src_dir.exists():
            for child in src_dir.iterdir():
                if child.is_dir() and not child.name.startswith("."):
                    candidates.append(child)

        for candidate in candidates:
            resolved = str(candidate.resolve())
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)

            files = []
            if candidate.is_dir():
                try:
                    files = [p.name for p in candidate.iterdir() if p.is_file()]
                except Exception:
                    files = []
            language = self._detect_language(candidate) if candidate.is_dir() else "unknown"
            entry_points = self._detect_entry_points(candidate, language, repository_root) if candidate.is_dir() else []
            classification = self._classify_module(candidate, repository_root, language, files, entry_points)

            modules.append(
                {
                    "name": candidate.name or repository_root.name,
                    "path": str(candidate),
                    "classification": classification,
                    "language": language,
                    "entry_point_count": len(entry_points),
                    "is_service": resolved in service_paths,
                }
            )

        return modules
    
    def _detect_language(self, path: Path) -> str:
        """Detect the primary language of a service."""
        if path.is_file():
            ext = path.suffix
            if ext == ".py":
                return "python"
            if ext in {".js", ".jsx", ".ts", ".tsx"}:
                return "javascript"
            if ext == ".java":
                return "java"
            return "unknown"
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
        service: Dict[str, Any],
        repository_root: Path,
    ) -> Dict[str, Any]:
        """Analyze dependencies for a single service."""
        dependencies = []
        api_endpoints = []
        databases = []
        message_queues = []
        
        path = Path(str(service.get("path") or ""))
        service_id = str(service.get("id") or "")
        service_language = str(service.get("language") or "")
        service_module = str(service.get("module_name") or "")
        
        # Get all code files
        if path.is_file():
            code_files = [path]
        else:
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
                normalized_target = self._normalize_dependency_target(
                    dep,
                    service_language=service_language,
                    service_module=service_module,
                    service_path=str(path),
                )
                dependencies.append({
                    "source": service_id,
                    "target": normalized_target,
                    "type": "module_import" if service_module else "import",
                    "file": file_str,
                    "original_target": dep,
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

    def _normalize_dependency_target(
        self,
        dep: str,
        service_language: str,
        service_module: str,
        service_path: Optional[str] = None,
    ) -> str:
        raw = str(dep or "").strip()
        if not raw:
            return raw
        if service_language != "python" or not service_module:
            return raw
        if not raw.startswith("."):
            return raw

        level = len(raw) - len(raw.lstrip("."))
        remainder = raw[level:]
        current_parts = service_module.split(".")
        is_package_root = str(service_path or "").replace("\\", "/").endswith("/__init__.py")
        package_parts = current_parts if is_package_root else current_parts[:-1]
        if level > 1:
            package_parts = package_parts[: max(0, len(package_parts) - (level - 1))]
        normalized_parts = [*package_parts]
        if remainder:
            normalized_parts.extend([part for part in remainder.split(".") if part])
        return ".".join(normalized_parts)
    
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

            # Spring MVC endpoint mappings (inbound API surface)
            spring_mappings = self._detect_spring_mvc_endpoints(content, file_path)
            api_calls.extend(spring_mappings)
        
        except Exception as e:
            logger.error(f"Error detecting API calls in {file_path}: {e}")
        
        return api_calls

    def _detect_spring_mvc_endpoints(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Detect Spring MVC controller endpoints from annotations."""
        endpoints: List[Dict[str, Any]] = []

        # Keep this light-weight (regex only), but good enough for common @*Mapping annotations.
        class_level_prefixes: List[str] = []
        class_mapping_pattern = re.compile(
            r"@RequestMapping\s*\(\s*(?:value\s*=\s*)?[\"']([^\"']*)[\"'][^)]*\)\s*(?:public\s+)?(?:abstract\s+)?class\s+\w+",
            re.MULTILINE,
        )
        for match in class_mapping_pattern.finditer(content):
            prefix = (match.group(1) or "").strip()
            if prefix and prefix not in class_level_prefixes:
                class_level_prefixes.append(prefix)
        if not class_level_prefixes:
            class_level_prefixes = [""]

        mapping_patterns = [
            (re.compile(r"@GetMapping\s*\(\s*(?:value\s*=\s*)?[\"']([^\"']*)[\"']"), "GET"),
            (re.compile(r"@PostMapping\s*\(\s*(?:value\s*=\s*)?[\"']([^\"']*)[\"']"), "POST"),
            (re.compile(r"@PutMapping\s*\(\s*(?:value\s*=\s*)?[\"']([^\"']*)[\"']"), "PUT"),
            (re.compile(r"@DeleteMapping\s*\(\s*(?:value\s*=\s*)?[\"']([^\"']*)[\"']"), "DELETE"),
            (re.compile(r"@PatchMapping\s*\(\s*(?:value\s*=\s*)?[\"']([^\"']*)[\"']"), "PATCH"),
        ]

        # @RequestMapping(method=..., value="...") variants
        request_mapping_pattern = re.compile(
            r"@RequestMapping\s*\(([^)]*)\)",
            re.MULTILINE | re.DOTALL,
        )
        request_method_pattern = re.compile(r"RequestMethod\.(GET|POST|PUT|DELETE|PATCH)")
        request_value_pattern = re.compile(r"(?:value|path)\s*=\s*[\"']([^\"']*)[\"']")

        seen: Set[Tuple[str, str]] = set()
        for pattern, method in mapping_patterns:
            for match in pattern.finditer(content):
                path = (match.group(1) or "").strip()
                full_paths = self._join_spring_paths(class_level_prefixes, path)
                for full_path in full_paths:
                    key = (method, full_path)
                    if key in seen:
                        continue
                    endpoints.append(
                        {
                            "endpoint": full_path,
                            "method": method,
                            "file": file_path,
                            "language": "java-spring",
                            "type": "inbound_endpoint",
                        }
                    )
                    seen.add(key)

        for match in request_mapping_pattern.finditer(content):
            annotation_body = match.group(1) or ""
            methods = request_method_pattern.findall(annotation_body)
            values = request_value_pattern.findall(annotation_body)
            if not values:
                continue
            resolved_methods = methods or ["GET"]
            for method in resolved_methods:
                for value in values:
                    for full_path in self._join_spring_paths(class_level_prefixes, value.strip()):
                        key = (method, full_path)
                        if key in seen:
                            continue
                        endpoints.append(
                            {
                                "endpoint": full_path,
                                "method": method,
                                "file": file_path,
                                "language": "java-spring",
                                "type": "inbound_endpoint",
                            }
                        )
                        seen.add(key)

        return endpoints

    def _join_spring_paths(self, prefixes: List[str], path: str) -> List[str]:
        def normalize(segment: str) -> str:
            seg = (segment or "").strip()
            if not seg:
                return ""
            if not seg.startswith("/"):
                seg = f"/{seg}"
            return seg.rstrip("/") or "/"

        path_norm = normalize(path)
        if not prefixes:
            return [path_norm or "/"]

        out: List[str] = []
        for prefix in prefixes:
            prefix_norm = normalize(prefix)
            if not prefix_norm or prefix_norm == "/":
                candidate = path_norm or "/"
            elif not path_norm or path_norm == "/":
                candidate = prefix_norm
            else:
                candidate = f"{prefix_norm}{path_norm}"
            out.append(candidate)
        return list(dict.fromkeys(out))
    
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
