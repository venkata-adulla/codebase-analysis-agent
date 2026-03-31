"""
Static architecture analysis: stack detection, coding-style metrics, risks, diagram graph.
Combines manifest parsing, folder heuristics, and optional Neo4j metrics.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
import tomllib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

MAX_FILES_STYLE = 120
MAX_FILE_BYTES = 256_000
LARGE_FILE_LINES = 500


# package_name -> (category, display_name, base_confidence)
PACKAGE_MAP: Dict[str, Tuple[str, str, float]] = {
    # Frontend
    "react": ("frontend", "React", 0.92),
    "next": ("frontend", "Next.js", 0.9),
    "vue": ("frontend", "Vue", 0.9),
    "angular": ("frontend", "Angular", 0.9),
    "@angular/core": ("frontend", "Angular", 0.92),
    "svelte": ("frontend", "Svelte", 0.88),
    "nuxt": ("frontend", "Nuxt", 0.88),
    # Backend
    "fastapi": ("backend", "FastAPI", 0.95),
    "flask": ("backend", "Flask", 0.93),
    "django": ("backend", "Django", 0.95),
    "starlette": ("backend", "Starlette", 0.85),
    "uvicorn": ("backend", "Uvicorn", 0.7),
    "express": ("backend", "Express", 0.92),
    "nestjs": ("backend", "NestJS", 0.9),
    "@nestjs/core": ("backend", "NestJS", 0.92),
    "koa": ("backend", "Koa", 0.85),
    "spring-boot": ("backend", "Spring Boot", 0.9),
    "gin-gonic/gin": ("backend", "Gin", 0.88),
    "rails": ("backend", "Ruby on Rails", 0.92),
    "laravel": ("backend", "Laravel", 0.9),
    # Data stores
    "pg": ("database", "PostgreSQL", 0.85),
    "psycopg2": ("database", "PostgreSQL", 0.9),
    "asyncpg": ("database", "PostgreSQL", 0.88),
    "sqlalchemy": ("database", "SQLAlchemy", 0.75),
    "pymongo": ("database", "MongoDB", 0.9),
    "mongoose": ("database", "MongoDB", 0.88),
    "redis": ("other", "Redis", 0.92),
    "ioredis": ("other", "Redis", 0.88),
    "celery": ("other", "Celery", 0.9),
    "bull": ("other", "Bull (queue)", 0.85),
    "kafka-python": ("other", "Kafka", 0.85),
    "pika": ("other", "RabbitMQ", 0.8),
    "pytest": ("other", "pytest", 0.88),
    "jest": ("other", "Jest", 0.88),
    "vitest": ("other", "Vitest", 0.85),
}

DOCKER_IMAGE_HINTS = [
    ("postgres", "database", "PostgreSQL", 0.9),
    ("mysql", "database", "MySQL", 0.88),
    ("mongo", "database", "MongoDB", 0.88),
    ("redis", "other", "Redis", 0.9),
    ("neo4j", "other", "Neo4j", 0.88),
    ("qdrant", "other", "Qdrant", 0.85),
]

# Maven <artifactId> -> (category, display_name, confidence)
MAVEN_ARTIFACT_HINTS: Dict[str, Tuple[str, str, float]] = {
    "spring-boot-starter-web": ("backend", "Spring MVC / REST", 0.92),
    "spring-boot-starter-data-jpa": ("backend", "Spring Data JPA", 0.9),
    "spring-boot-starter-thymeleaf": ("backend", "Thymeleaf", 0.88),
    "spring-boot-starter-actuator": ("backend", "Spring Boot Actuator", 0.85),
    "spring-boot-starter-validation": ("backend", "Bean Validation", 0.78),
    "spring-boot-starter-security": ("backend", "Spring Security", 0.88),
    "mysql-connector-j": ("database", "MySQL", 0.9),
    "postgresql": ("database", "PostgreSQL", 0.9),
    "h2": ("database", "H2", 0.85),
    "mongodb": ("database", "MongoDB", 0.85),
    "flyway-core": ("other", "Flyway", 0.8),
    "liquibase-core": ("other", "Liquibase", 0.8),
    "spring-boot-starter-test": ("other", "Spring Test", 0.65),
}


@dataclass
class StackItem:
    name: str
    category: str
    confidence: float
    source: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "confidence": round(self.confidence, 3),
            "source": self.source,
        }


def _walk_repo_files(root: Path, extensions: Set[str], limit: int) -> List[Path]:
    out: List[Path] = []
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            # skip heavy dirs
            skip = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build", ".next"}
            dirnames[:] = [d for d in dirnames if d not in skip]
            for fn in filenames:
                if len(out) >= limit:
                    return out
                p = Path(dirpath) / fn
                if p.suffix.lower() in extensions:
                    out.append(p)
    except Exception as exc:
        logger.warning("walk_repo_files: %s", exc)
    return out


def _read_text_safe(path: Path, max_bytes: int = MAX_FILE_BYTES) -> str:
    try:
        raw = path.read_bytes()[:max_bytes]
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _parse_package_json(path: Path) -> Dict[str, Any]:
    text = _read_text_safe(path)
    if not text.strip():
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _parse_requirements_txt(path: Path) -> List[str]:
    text = _read_text_safe(path)
    names: List[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([a-zA-Z0-9_\-\.]+)", line)
        if m:
            names.append(m.group(1).lower().replace("_", "-"))
    return names


def _parse_pyproject_deps(path: Path) -> List[str]:
    text = _read_text_safe(path)
    if not text.strip():
        return []
    names: List[str] = []
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []

    tool = data.get("tool") or {}
    poetry = tool.get("poetry") or {}
    poetry_deps = poetry.get("dependencies") or {}
    if isinstance(poetry_deps, dict):
        for key in poetry_deps.keys():
            dep = str(key).lower().replace("_", "-")
            if dep not in ("python", "python3"):
                names.append(dep)

    project = data.get("project") or {}
    project_deps = project.get("dependencies") or []
    if isinstance(project_deps, list):
        for dep in project_deps:
            m = re.match(r"^\s*([a-zA-Z0-9_\-\.]+)", str(dep))
            if m:
                names.append(m.group(1).lower().replace("_", "-"))

    optional = project.get("optional-dependencies") or {}
    if isinstance(optional, dict):
        for vals in optional.values():
            if not isinstance(vals, list):
                continue
            for dep in vals:
                m = re.match(r"^\s*([a-zA-Z0-9_\-\.]+)", str(dep))
                if m:
                    names.append(m.group(1).lower().replace("_", "-"))

    dep_groups = data.get("dependency-groups") or {}
    if isinstance(dep_groups, dict):
        for vals in dep_groups.values():
            if not isinstance(vals, list):
                continue
            for dep in vals:
                m = re.match(r"^\s*([a-zA-Z0-9_\-\.]+)", str(dep))
                if m:
                    names.append(m.group(1).lower().replace("_", "-"))

    return list(dict.fromkeys(names))


def _is_python_project(path: Path) -> bool:
    text = _read_text_safe(path)
    if not text.strip():
        return False
    lowered = text.lower()
    return any(
        token in lowered
        for token in (
            "requires-python",
            "[project]",
            "[tool.poetry]",
            "[tool.flit",
            "[tool.hatch",
            "build-backend",
        )
    )


def _parse_maven_pom_artifact_ids(path: Path) -> List[str]:
    text = _read_text_safe(path)
    if not text.strip():
        return []
    found: List[str] = []
    for m in re.finditer(r"<artifactId>([^<]+)</artifactId>", text):
        a = (m.group(1) or "").strip()
        if not a or a.startswith("${"):
            continue
        found.append(a.lower())
    return list(dict.fromkeys(found))


def _gradle_dependency_hints(path: Path) -> List[str]:
    """Light scan of Gradle files for known dependency names."""
    text = _read_text_safe(path)
    if not text.strip():
        return []
    lower = text.lower()
    hints: List[str] = []
    if "spring-boot" in lower or "org.springframework" in lower:
        hints.append("spring-boot-starter-web")
    if "springframework.data.jpa" in lower or "spring-data-jpa" in lower:
        hints.append("spring-boot-starter-data-jpa")
    if "mysql" in lower and "connector" in lower:
        hints.append("mysql-connector-j")
    if "postgresql" in lower:
        hints.append("postgresql")
    if "com.h2database" in lower or " h2" in lower:
        hints.append("h2")
    return list(dict.fromkeys(hints))


def _parse_go_mod(path: Path) -> List[str]:
    text = _read_text_safe(path)
    mods: List[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("require "):
            rest = line[8:].strip()
            mods.append(rest.split()[0].lower())
    return mods


def _parse_docker_compose(path: Path) -> List[Tuple[str, str]]:
    """Return list of (raw_image_fragment, context) for hinting."""
    text = _read_text_safe(path)
    found: List[Tuple[str, str]] = []
    for m in re.finditer(r"image:\s*([^\s#]+)", text, re.IGNORECASE):
        found.append((m.group(1).strip().lower(), "docker-compose"))
    return found


def _folder_hints(root: Path) -> Dict[str, float]:
    hints: Dict[str, float] = defaultdict(float)
    try:
        for name in os.listdir(root):
            low = name.lower()
            if low in ("frontend", "web", "client", "ui"):
                hints["frontend"] = max(hints["frontend"], 0.55)
            if low in ("backend", "api", "server", "services"):
                hints["backend"] = max(hints["backend"], 0.55)
            if low in ("infra", "deploy", "docker"):
                hints["infra"] = max(hints["infra"], 0.45)
    except Exception:
        pass
    return dict(hints)


def _match_package(name: str) -> Optional[Tuple[str, str, float]]:
    key = name.lower().strip()
    if key in PACKAGE_MAP:
        return PACKAGE_MAP[key]
    # strip version spec
    base = key.split("[")[0]
    if base in PACKAGE_MAP:
        return PACKAGE_MAP[base]
    for pkg, tpl in PACKAGE_MAP.items():
        if pkg in base or base.startswith(pkg + "-"):
            return tpl
    return None


def detect_stack(root: Path) -> Dict[str, Any]:
    """Scan manifests and docker-compose for technologies."""
    items: List[StackItem] = []
    seen: Set[str] = set()

    def add(name: str, category: str, conf: float, source: str) -> None:
        key = f"{category}:{name.lower()}"
        if key in seen:
            return
        seen.add(key)
        items.append(StackItem(name=name, category=category, confidence=min(conf, 0.99), source=source))

    manifests: List[str] = []

    for rel in ("package.json", "frontend/package.json", "web/package.json", "client/package.json"):
        p = root / rel
        if p.is_file():
            manifests.append(str(p))
            data = _parse_package_json(p)
            for section in ("dependencies", "devDependencies", "peerDependencies"):
                block = data.get(section) or {}
                if not isinstance(block, dict):
                    continue
                dev_penalty = 0.85 if section == "devDependencies" else 1.0
                for pkg_name in block.keys():
                    hit = _match_package(str(pkg_name))
                    if hit:
                        cat, disp, base = hit
                        add(disp, cat, base * dev_penalty, f"package.json:{section}")
                    elif "react" in pkg_name.lower():
                        add("React ecosystem", "frontend", 0.65 * dev_penalty, f"package.json:{section}")

    for rel in ("requirements.txt", "backend/requirements.txt"):
        p = root / rel
        if p.is_file():
            manifests.append(str(p))
            for req in _parse_requirements_txt(p):
                hit = _match_package(req)
                if hit:
                    cat, disp, base = hit
                    add(disp, cat, base, "requirements.txt")

    for rel in ("pyproject.toml", "backend/pyproject.toml"):
        p = root / rel
        if p.is_file():
            manifests.append(str(p))
            for req in _parse_pyproject_deps(p):
                hit = _match_package(req)
                if hit:
                    cat, disp, base = hit
                    add(disp, cat, base * 0.92, "pyproject.toml")
            if _is_python_project(p) and not any(i.category == "backend" for i in items):
                add("Python project", "backend", 0.62, "pyproject.toml:project")

    for rel in ("go.mod",):
        p = root / rel
        if p.is_file():
            manifests.append(str(p))
            for m in _parse_go_mod(p):
                hit = _match_package(m.split("/")[-1])
                if hit:
                    cat, disp, base = hit
                    add(disp, cat, base * 0.9, "go.mod")

    for rel in ("pom.xml",):
        p = root / rel
        if p.is_file():
            manifests.append(str(p))
            for art in _parse_maven_pom_artifact_ids(p):
                tpl = MAVEN_ARTIFACT_HINTS.get(art)
                if tpl:
                    cat, disp, conf = tpl
                    add(disp, cat, conf, "pom.xml")
                elif "spring-boot-starter" in art:
                    add("Spring Boot (" + art.replace("spring-boot-starter-", "") + ")", "backend", 0.8, "pom.xml")

    for rel in ("build.gradle", "build.gradle.kts", "settings.gradle.kts"):
        p = root / rel
        if p.is_file():
            manifests.append(str(p))
            for hint_art in _gradle_dependency_hints(p):
                tpl = MAVEN_ARTIFACT_HINTS.get(hint_art)
                if tpl:
                    cat, disp, conf = tpl
                    add(disp, cat, conf * 0.9, p.name)

    for rel in ("docker-compose.yml", "docker-compose.yaml", "compose.yaml", "compose.yml"):
        p = root / rel
        if p.is_file():
            manifests.append(str(p))
            for img, src in _parse_docker_compose(p):
                for fragment, cat, disp, conf in DOCKER_IMAGE_HINTS:
                    if fragment in img:
                        add(disp, cat, conf, src)

    fh = _folder_hints(root)
    if fh.get("frontend", 0) > 0.4 and not any(i.category == "frontend" for i in items):
        add("Web client (folder layout)", "frontend", 0.5, "folder_structure")
    if fh.get("backend", 0) > 0.4 and not any(i.category == "backend" for i in items):
        add("API / server (folder layout)", "backend", 0.5, "folder_structure")

    by_cat: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for it in sorted(items, key=lambda x: -x.confidence):
        by_cat[it.category].append(it.to_dict())

    logger.info(
        "Architecture stack detection: %d items, manifests=%s",
        len(items),
        manifests[:8],
    )
    return {
        "items": [i.to_dict() for i in items],
        "by_category": dict(by_cat),
        "manifests_scanned": manifests,
    }


def _count_py_style(path: Path) -> Dict[str, Any]:
    lines_in_funcs: List[int] = []
    counters: Dict[str, int] = {"classes": 0, "functions": 0}
    try:
        tree = ast.parse(_read_text_safe(path))
    except SyntaxError:
        return {}

    class Visitor(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            counters["classes"] += 1
            self.generic_visit(node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            counters["functions"] += 1
            try:
                end = getattr(node, "end_lineno", None) or node.lineno
                lines_in_funcs.append(max(1, end - node.lineno + 1))
            except Exception:
                lines_in_funcs.append(1)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            counters["functions"] += 1
            try:
                end = getattr(node, "end_lineno", None) or node.lineno
                lines_in_funcs.append(max(1, end - node.lineno + 1))
            except Exception:
                lines_in_funcs.append(1)
            self.generic_visit(node)

    Visitor().visit(tree)
    return {
        "classes": counters["classes"],
        "functions": counters["functions"],
        "func_lines": lines_in_funcs,
    }


def _count_ts_js_style(path: Path) -> Dict[str, Any]:
    text = _read_text_safe(path)
    if not text:
        return {}
    # Heuristic: function declarations, arrow fns, classes
    functions = len(re.findall(r"\bfunction\s+\w+\s*\(", text))
    functions += len(re.findall(r"=>\s*\{?", text))
    functions += len(re.findall(r"async\s+function\b", text))
    classes = len(re.findall(r"\bclass\s+\w+", text))
    lines = text.count("\n") + 1
    return {
        "classes": classes,
        "functions": max(functions, 0),
        "file_lines": lines,
    }


def _count_java_style(path: Path) -> Dict[str, Any]:
    text = _read_text_safe(path)
    if not text:
        return {}
    types = len(re.findall(r"\b(class|interface|enum|record)\s+([A-Za-z_][\w]*)\b", text))
    methods = len(
        re.findall(
            r"\b(public|protected|private)\s+[\w<>,\s\[\].@]+\s+(\w+)\s*\([^)]*\)\s*(?:throws|\{)",
            text,
        )
    )
    lines = text.count("\n") + 1
    return {
        "classes": types,
        "functions": max(methods, 0),
        "file_lines": lines,
    }


def analyze_coding_style(root: Path) -> Dict[str, Any]:
    py_files = _walk_repo_files(root, {".py"}, MAX_FILES_STYLE // 2)
    ts_files = _walk_repo_files(root, {".ts", ".tsx", ".js", ".jsx"}, MAX_FILES_STYLE // 2)
    java_files = _walk_repo_files(root, {".java"}, MAX_FILES_STYLE // 2)

    total_classes = 0
    total_functions = 0
    all_func_lines: List[int] = []
    large_files: List[Dict[str, Any]] = []

    for p in py_files:
        n = len(_read_text_safe(p).splitlines())
        if n >= LARGE_FILE_LINES:
            large_files.append({"path": str(p.relative_to(root)), "lines": n, "language": "python"})
        st = _count_py_style(p)
        if st:
            total_classes += st.get("classes", 0)
            total_functions += st.get("functions", 0)
            all_func_lines.extend(st.get("func_lines") or [])

    for p in ts_files:
        n = len(_read_text_safe(p).splitlines())
        if n >= LARGE_FILE_LINES:
            large_files.append({"path": str(p.relative_to(root)), "lines": n, "language": "typescript/javascript"})
        st = _count_ts_js_style(p)
        total_classes += st.get("classes", 0)
        total_functions += st.get("functions", 0)
        if st.get("functions"):
            all_func_lines.append(max(8, n // max(1, st["functions"])))

    for p in java_files:
        n = len(_read_text_safe(p).splitlines())
        if n >= LARGE_FILE_LINES:
            large_files.append({"path": str(p.relative_to(root)), "lines": n, "language": "java"})
        st = _count_java_style(p)
        total_classes += st.get("classes", 0)
        total_functions += st.get("functions", 0)
        if st.get("functions"):
            all_func_lines.append(max(8, n // max(1, st["functions"])))

    denom = total_classes + total_functions
    class_ratio = (total_classes / denom) if denom else 0.0
    avg_fn = sum(all_func_lines) / len(all_func_lines) if all_func_lines else 0.0

    if class_ratio >= 0.35:
        label = "Primarily object-oriented"
    elif class_ratio <= 0.12:
        label = "Primarily functional / procedural"
    else:
        label = "Mixed style"

    modularity = "high" if avg_fn < 35 and len(large_files) < 3 else ("medium" if avg_fn < 55 else "low")

    metrics = {
        "class_count_estimate": total_classes,
        "function_count_estimate": total_functions,
        "class_ratio": round(class_ratio, 4),
        "avg_function_lines_estimate": round(avg_fn, 1),
        "files_sampled": len(py_files) + len(ts_files) + len(java_files),
        "modularity_hint": modularity,
        "label": label,
        "large_files": sorted(large_files, key=lambda x: -x["lines"])[:15],
    }
    logger.info(
        "Coding style: label=%s class_ratio=%s avg_fn=%.1f large=%d",
        label,
        metrics["class_ratio"],
        avg_fn,
        len(large_files),
    )
    return metrics


def _graph_metrics(repository_id: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"edge_count": 0, "node_count": 0, "cycles_approx": None}
    try:
        from services.graph_service import GraphService

        gs = GraphService()
        data = gs.get_dependency_graph(repository_id)
        edges = data.get("edges") or []
        nodes = data.get("nodes") or []
        out["edge_count"] = len(edges)
        out["node_count"] = len(nodes)
        arch = data.get("architecture_summary") or {}
        if isinstance(arch, dict) and arch.get("cycle_count") is not None:
            out["cycles_approx"] = arch.get("cycle_count")
    except Exception as exc:
        logger.info("Architecture: graph metrics unavailable: %s", exc)
    return out


def analyze_risks(
    root: Path,
    stack: Dict[str, Any],
    style: Dict[str, Any],
    repository_id: str,
) -> Dict[str, Any]:
    risks: List[Dict[str, Any]] = []
    good: List[str] = []
    missing: List[str] = []

    gm = _graph_metrics(repository_id)
    nodes_n = gm.get("node_count") or 0
    edges_n = gm.get("edge_count") or 0
    if nodes_n > 2 and edges_n > 0:
        ratio = edges_n / max(nodes_n, 1)
        if ratio > 4:
            risks.append(
                {
                    "id": "high-coupling",
                    "severity": "high",
                    "title": "Dense dependency graph",
                    "detail": f"Approximately {edges_n} edges among {nodes_n} services suggests high coupling.",
                    "category": "architecture",
                }
            )
        elif ratio < 1.2 and nodes_n > 5:
            good.append("Service graph appears relatively sparse (lower interconnection density).")

    cy = gm.get("cycles_approx")
    if isinstance(cy, (int, float)) and cy > 0:
        risks.append(
            {
                "id": "cycles",
                "severity": "medium",
                "title": "Dependency cycles detected",
                "detail": f"Graph analysis reports about {int(cy)} cycle(s).",
                "category": "architecture",
            }
        )

    for lf in style.get("large_files") or []:
        if lf.get("lines", 0) >= 800:
            risks.append(
                {
                    "id": f"large-file-{lf['path']}",
                    "severity": "medium",
                    "title": f"Very large file: {lf['path']}",
                    "detail": f"~{lf['lines']} lines — hard to review and change safely.",
                    "category": "code",
                }
            )

    items = stack.get("items") or []
    names = " ".join(i.get("name", "").lower() for i in items)
    pom_java_tests = False
    if (root / "pom.xml").is_file():
        arts = _parse_maven_pom_artifact_ids(root / "pom.xml")
        pom_java_tests = any("junit" in a for a in arts) or "spring-boot-starter-test" in arts
        if pom_java_tests:
            good.append("Java test dependencies (JUnit / Spring Test) present in pom.xml.")
    if not any(
        p in names for p in ("jest", "pytest", "vitest", "mocha", "cypress", "unittest", "nose2")
    ) and not pom_java_tests:
        missing.append("Automated test frameworks not clearly identified in manifests (add or document tests).")

    if any("docker" in (i.get("source") or "") for i in items):
        good.append("Container images declared (docker-compose), aiding reproducible environments.")

    fe = sum(1 for i in items if i.get("category") == "frontend")
    be = sum(1 for i in items if i.get("category") == "backend")
    if fe and be:
        good.append("Separate frontend and backend technologies detected — supports layered delivery.")

    if not fe and be:
        missing.append("No dedicated frontend stack detected — may be API-only or monolith; verify structure.")

    logger.info(
        "Risk scan: risks=%d good=%d missing=%d graph_nodes=%s",
        len(risks),
        len(good),
        len(missing),
        nodes_n,
    )
    return {
        "risks": risks[:25],
        "best_practices_observed": good[:12],
        "best_practices_missing": missing[:12],
        "graph_metrics": gm,
    }


def _layout_architecture_positions(node_ids: List[str]) -> Dict[str, Tuple[float, float]]:
    """
    Normalized 0–100 coordinates (x = horizontal %, y = vertical %) for the logical view.
    Keeps edges short and readable; pairs like backend+external use a horizontal layout.
    """
    ids = node_ids
    n = len(ids)
    if n == 0:
        return {}
    if n == 1:
        return {ids[0]: (50.0, 50.0)}
    if n == 2:
        a, b = ids[0], ids[1]
        if {a, b} == {"backend", "external"}:
            return {"backend": (34.0, 50.0), "external": (66.0, 50.0)}
        if {a, b} == {"backend", "database"}:
            return {"backend": (50.0, 28.0), "database": (50.0, 74.0)}
        if {a, b} == {"frontend", "backend"}:
            return {"frontend": (50.0, 28.0), "backend": (50.0, 68.0)}
        return {ids[0]: (28.0, 50.0), ids[1]: (72.0, 50.0)}
    if n == 3:
        s = set(ids)
        if s == {"frontend", "backend", "database"}:
            return {"frontend": (50.0, 16.0), "backend": (50.0, 48.0), "database": (50.0, 80.0)}
        if s == {"backend", "database", "external"}:
            return {"backend": (36.0, 36.0), "database": (50.0, 78.0), "external": (68.0, 36.0)}
        if s == {"frontend", "backend", "external"}:
            return {"frontend": (24.0, 48.0), "backend": (52.0, 48.0), "external": (78.0, 48.0)}
        # default: vertical stack in declared order
        return {ids[0]: (50.0, 22.0), ids[1]: (50.0, 52.0), ids[2]: (50.0, 82.0)}
    # four layers: frontend top, backend center, database bottom, external to the right of backend
    if n == 4 and set(ids) == {"frontend", "backend", "database", "external"}:
        return {
            "frontend": (50.0, 12.0),
            "backend": (42.0, 44.0),
            "database": (50.0, 78.0),
            "external": (76.0, 44.0),
        }
    # fallback grid
    out: Dict[str, Tuple[float, float]] = {}
    for i, nid in enumerate(ids):
        row, col = divmod(i, 2)
        out[nid] = (32.0 + col * 36.0, 28.0 + row * 40.0)
    return out


def build_architecture_diagram(stack: Dict[str, Any]) -> Dict[str, Any]:
    """High-level boxes + edges (not the service dependency graph)."""
    by_cat = stack.get("by_category") or {}
    fe = [x["name"] for x in by_cat.get("frontend", [])][:4]
    be = [x["name"] for x in by_cat.get("backend", [])][:4]
    db = [x["name"] for x in by_cat.get("database", [])][:3]
    ot = [x["name"] for x in by_cat.get("other", [])][:4]

    if not fe and not be:
        be = be or ["Application"]

    pending: List[Tuple[str, str, str, str]] = []
    if fe:
        pending.append(("frontend", "Frontend", ", ".join(fe), "frontend"))
    if be:
        backend_label = "Backend / API" if fe or db or ot else "Application"
        pending.append(("backend", backend_label, ", ".join(be), "backend"))
    if db:
        pending.append(("database", "Data stores", ", ".join(db), "database"))
    if ot:
        pending.append(("external", "External & infra", ", ".join(ot), "other"))

    positions = _layout_architecture_positions([p[0] for p in pending])
    nodes: List[Dict[str, Any]] = []
    for nid, label, sub, ntype in pending:
        x, y = positions.get(nid, (50.0, 50.0))
        nodes.append(
            {
                "id": nid,
                "label": label,
                "sublabel": sub,
                "type": ntype,
                "x": x,
                "y": y,
            }
        )

    edges: List[Dict[str, Any]] = []
    if fe and be:
        edges.append({"id": "e1", "source": "frontend", "target": "backend", "label": "HTTP / API"})
    if be and db:
        edges.append({"id": "e2", "source": "backend", "target": "database", "label": "Data access"})
    if be and ot:
        edges.append({"id": "e3", "source": "backend", "target": "external", "label": "Side services"})
    if not edges and len(nodes) == 2:
        edges.append({"id": "e4", "source": nodes[0]["id"], "target": nodes[1]["id"], "label": "Relationship"})

    return {"nodes": nodes, "edges": edges}


def _repo_context_summary(root: Path) -> Dict[str, Any]:
    """Lightweight facts for LLM narratives (no extra network calls)."""
    dirs = sorted(
        [d.name for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")]
    )[:28]
    readme_excerpt = ""
    for pr in ("README.md", "readme.md", "README.rst"):
        rp = root / pr
        if rp.is_file():
            readme_excerpt = _read_text_safe(rp)[:2000]
            break
    build_files = [
        x
        for x in (
            "pom.xml",
            "build.gradle",
            "build.gradle.kts",
            "package.json",
            "pyproject.toml",
            "go.mod",
        )
        if (root / x).is_file()
    ]
    java_main = root / "src" / "main" / "java"
    java_packages_hint = ""
    if java_main.is_dir():
        n_java = sum(1 for _ in java_main.rglob("*.java"))
        java_packages_hint = f"{n_java} Java files under src/main/java"
    return {
        "folder_name": root.name,
        "top_level_directories": dirs,
        "readme_excerpt": readme_excerpt,
        "build_files": build_files,
        "java_sources_hint": java_packages_hint,
    }


def run_static_architecture_analysis(repository_id: str, repo_path: str) -> Dict[str, Any]:
    root = Path(repo_path)
    if not root.is_dir():
        raise ValueError(f"Repository path not found: {repo_path}")

    stack = detect_stack(root)
    style = analyze_coding_style(root)
    risks_block = analyze_risks(root, stack, style, repository_id)
    diagram = build_architecture_diagram(stack)
    repository_context = _repo_context_summary(root)

    return {
        "repository_id": repository_id,
        "diagram": diagram,
        "technology_stack": stack,
        "coding_style": style,
        "risks_and_practices": risks_block,
        "repository_context": repository_context,
        "detection_log": {
            "frameworks_detected": [i.get("name") for i in stack.get("items", [])],
            "classification": {k: len(v) for k, v in (stack.get("by_category") or {}).items()},
        },
    }


class ArchitectureAnalyzer:
    """
    Produces architecture-category debt items from the in-memory dependency graph
    and service list (same inputs as the tech-debt pipeline).
    """

    def analyze(
        self,
        repository_id: str,
        services: List[Dict[str, Any]],
        dependency_graph: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        dg = dependency_graph if isinstance(dependency_graph, dict) else None
        nodes = (dg or {}).get("nodes") or []
        edges = (dg or {}).get("edges") or []
        n_count = len(nodes)
        e_count = len(edges)

        if n_count > 2 and e_count > 0:
            ratio = e_count / max(n_count, 1)
            if ratio > 4.0:
                items.append(
                    {
                        "id": f"arch-high-coupling-{repository_id[:12]}",
                        "category": "architecture",
                        "severity": "high",
                        "title": "Dense dependency graph",
                        "description": (
                            f"Approximately {e_count} edges among {n_count} services/modules suggests high coupling."
                        ),
                        "impact_score": min(ratio / 8.0, 1.0),
                        "effort_estimate": "weeks",
                    }
                )

        arch_summary = (dg or {}).get("architecture_summary") if dg else None
        if isinstance(arch_summary, dict):
            cy = arch_summary.get("cycle_count")
            if isinstance(cy, (int, float)) and cy > 0:
                items.append(
                    {
                        "id": f"arch-cycles-{repository_id[:12]}",
                        "category": "architecture",
                        "severity": "medium",
                        "title": "Dependency cycles detected",
                        "description": f"Graph analysis reports about {int(cy)} cycle(s) in the dependency structure.",
                        "impact_score": min(0.3 + cy * 0.05, 1.0),
                        "effort_estimate": "days",
                    }
                )

        # If the graph was not passed but we have a repo id, try live metrics (Neo4j-backed).
        if (not nodes or not edges) and repository_id:
            gm = _graph_metrics(repository_id)
            n2 = int(gm.get("node_count") or 0)
            e2 = int(gm.get("edge_count") or 0)
            if n2 > 2 and e2 > 0:
                ratio = e2 / max(n2, 1)
                if ratio > 4.0 and not any(i.get("id", "").startswith("arch-high-coupling") for i in items):
                    items.append(
                        {
                            "id": f"arch-high-coupling-gm-{repository_id[:12]}",
                            "category": "architecture",
                            "severity": "high",
                            "title": "Dense dependency graph",
                            "description": (
                                f"Approximately {e2} edges among {n2} services/modules suggests high coupling."
                            ),
                            "impact_score": min(ratio / 8.0, 1.0),
                            "effort_estimate": "weeks",
                        }
                    )
                cy = gm.get("cycles_approx")
                if isinstance(cy, (int, float)) and cy > 0 and not any(
                    i.get("id", "").startswith("arch-cycles") for i in items
                ):
                    items.append(
                        {
                            "id": f"arch-cycles-gm-{repository_id[:12]}",
                            "category": "architecture",
                            "severity": "medium",
                            "title": "Dependency cycles detected",
                            "description": f"Graph analysis reports about {int(cy)} cycle(s).",
                            "impact_score": min(0.3 + cy * 0.05, 1.0),
                            "effort_estimate": "days",
                        }
                    )

        svc_n = len(services) if services else 0
        if svc_n == 0 and n_count == 0:
            items.append(
                {
                    "id": f"arch-missing-context-{repository_id[:12]}",
                    "category": "architecture",
                    "severity": "low",
                    "title": "Limited architecture context",
                    "description": (
                        "No services and no graph nodes were provided; architecture-related debt signals are minimal."
                    ),
                    "impact_score": 0.2,
                    "effort_estimate": "hours",
                }
            )

        return items
