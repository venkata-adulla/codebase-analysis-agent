import os
from pathlib import Path
from typing import Any, Dict, List, Set


class TestCoverageAnalyzer:
    """Heuristic test-coverage analyzer when line coverage tooling is unavailable."""

    CODE_EXTS: Set[str] = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rb", ".php", ".cs"}
    TEST_FILE_HINTS: Set[str] = {
        "test_",
        "_test",
        ".spec.",
        ".test.",
        "tests.",
        "test.",
        "it_",
    }
    TEST_DIR_HINTS: Set[str] = {"test", "tests", "__tests__", "spec", "specs"}

    def analyze(self, repository_path: str) -> List[Dict[str, Any]]:
        root = Path(repository_path)
        if not root.is_dir():
            return []

        code_files = 0
        test_files = 0
        coverage_reports = 0

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", ".venv", "venv", "dist", "build", ".next"}]
            cur = Path(dirpath)
            in_test_dir = any(part.lower() in self.TEST_DIR_HINTS for part in cur.parts)

            for fn in filenames:
                p = cur / fn
                name_l = fn.lower()
                ext = p.suffix.lower()

                if name_l in {"coverage.xml", "jacoco.xml", "lcov.info", ".coverage"}:
                    coverage_reports += 1

                if ext not in self.CODE_EXTS:
                    continue
                code_files += 1

                if in_test_dir or any(h in name_l for h in self.TEST_FILE_HINTS):
                    test_files += 1

        if code_files == 0:
            return []

        ratio = test_files / max(code_files, 1)
        report_bonus = min(0.12, coverage_reports * 0.04)
        effective_ratio = min(1.0, ratio + report_bonus)

        # 0 debt = better coverage; this produces a meaningful score even without full coverage tooling.
        impact = max(0.05, min(1.0, 1.0 - (effective_ratio / 0.40)))
        if effective_ratio < 0.10:
            sev = "high"
            effort = "days"
            title = "Low automated test presence detected"
        elif effective_ratio < 0.22:
            sev = "medium"
            effort = "days"
            title = "Moderate automated test presence"
        else:
            sev = "low"
            effort = "hours"
            title = "Test presence detected (heuristic estimate)"

        return [
            {
                "category": "test_coverage",
                "severity": sev,
                "title": title,
                "description": (
                    f"Heuristic estimate from repository structure found {test_files} test-like files out of "
                    f"{code_files} code files (effective ratio ~{effective_ratio:.2f})."
                ),
                "impact_score": round(impact, 3),
                "effort_estimate": effort,
                "meta_data": {
                    "code_files": code_files,
                    "test_files": test_files,
                    "ratio": round(ratio, 4),
                    "coverage_reports_detected": coverage_reports,
                    "effective_ratio": round(effective_ratio, 4),
                    "method": "heuristic_test_file_ratio",
                },
            }
        ]
