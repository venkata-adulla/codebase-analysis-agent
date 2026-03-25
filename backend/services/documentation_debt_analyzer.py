import ast
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class DocumentationDebtAnalyzer:
    """Basic documentation debt checks for repository and Python modules."""

    def analyze(self, repository_path: str) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        root = Path(repository_path)
        if not root.exists():
            return items

        items.extend(self._check_repository_docs(root))
        items.extend(self._check_python_docstrings(root))
        return items

    def _check_repository_docs(self, root: Path) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        readme_files = list(root.glob("README*"))
        docs_dir = root / "docs"
        changelog_files = [*root.glob("CHANGELOG*"), *root.glob("CHANGES*")]

        if not readme_files:
            items.append(
                {
                    "id": f"doc_missing_readme_{root.name}",
                    "category": "documentation",
                    "severity": "high",
                    "title": "Missing repository README",
                    "description": "The repository does not appear to contain a top-level README file.",
                    "file_path": str(root),
                    "impact_score": 0.85,
                    "effort_estimate": "hours",
                }
            )
        if not docs_dir.exists():
            items.append(
                {
                    "id": f"doc_missing_docs_dir_{root.name}",
                    "category": "documentation",
                    "severity": "medium",
                    "title": "Missing dedicated docs folder",
                    "description": "No `docs/` directory was found, so maintainers may lack a clear place for deeper documentation.",
                    "file_path": str(root),
                    "impact_score": 0.45,
                    "effort_estimate": "hours",
                }
            )
        if not changelog_files:
            items.append(
                {
                    "id": f"doc_missing_changelog_{root.name}",
                    "category": "documentation",
                    "severity": "low",
                    "title": "Missing changelog or release notes",
                    "description": "No changelog/release-notes file was detected at the repository root.",
                    "file_path": str(root),
                    "impact_score": 0.25,
                    "effort_estimate": "hours",
                }
            )

        return items

    def _check_python_docstrings(self, root: Path) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        candidate_files = [
            path for path in root.rglob("*.py")
            if path.is_file() and not any(part in {"tests", "test", ".venv", "venv", "__pycache__"} for part in path.parts)
        ]

        for file_path in candidate_files[:250]:
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(content, filename=str(file_path))
            except Exception as exc:
                logger.debug("Documentation analyzer skipped %s: %s", file_path, exc)
                continue

            module_doc = ast.get_docstring(tree)
            public_defs = [
                node
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and not node.name.startswith("_")
            ]
            undocumented_public_defs = [node for node in public_defs if not ast.get_docstring(node)]

            if public_defs and not module_doc:
                items.append(
                    {
                        "id": f"doc_missing_module_{file_path}",
                        "category": "documentation",
                        "severity": "low",
                        "title": f"Missing module docstring: {file_path.name}",
                        "description": "This Python module exposes public symbols but has no module-level docstring.",
                        "file_path": str(file_path),
                        "line_start": 1,
                        "line_end": 1,
                        "impact_score": 0.2,
                        "effort_estimate": "hours",
                    }
                )

            if len(undocumented_public_defs) >= 3:
                names = ", ".join(node.name for node in undocumented_public_defs[:4])
                items.append(
                    {
                        "id": f"doc_missing_public_api_{file_path}",
                        "category": "documentation",
                        "severity": "medium",
                        "title": f"Undocumented public API in {file_path.name}",
                        "description": (
                            f"Public definitions without docstrings were detected ({names}"
                            f"{', ...' if len(undocumented_public_defs) > 4 else ''})."
                        ),
                        "file_path": str(file_path),
                        "line_start": undocumented_public_defs[0].lineno,
                        "line_end": undocumented_public_defs[-1].end_lineno or undocumented_public_defs[-1].lineno,
                        "impact_score": min(0.2 + 0.08 * len(undocumented_public_defs), 0.8),
                        "effort_estimate": "hours",
                        "metadata": {"undocumented_count": len(undocumented_public_defs)},
                    }
                )

        return items
