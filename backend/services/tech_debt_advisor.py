import re
from typing import Any, Dict


OVERALL_SCORE_WEIGHTS = {
    "code_quality": 0.30,
    "architecture": 0.25,
    "dependency": 0.20,
    "documentation": 0.15,
    "test_coverage": 0.10,
}

SEVERITY_WEIGHTS = {
    "low": 1.0,
    "medium": 2.5,
    "high": 5.0,
    "critical": 10.0,
}

# Human-readable breakdown for the tech-debt UI ("How this score was computed").
CATEGORY_COMPUTATION: Dict[str, Dict[str, Any]] = {
    "code_quality": {
        "feeds": (
            "Static analysis over parsed code elements (functions, classes, methods). "
            "Issues include long functions, high complexity, duplication, deep nesting, magic numbers, "
            "commented-out code, and similar maintainability findings."
        ),
        "steps": [
            "Each finding in this category becomes one debt item with a severity (low → critical) and an impact_score (0–1).",
            "Per item contribution = severity_weight × impact_score. Severity weights: low 1.0, medium 2.5, high 5.0, critical 10.0.",
            "Sum those contributions, then divide by (number of items in this category × 10) and multiply by 100. Cap at 100.",
            "This normalizes so more numerous or more severe issues together push the category score toward 100 (higher = more debt).",
        ],
        "no_issues": (
            "If there are zero debt items in this category, the score may instead be a small provisional value (2–6) "
            "from analysis coverage confidence, not from issues."
        ),
    },
    "architecture": {
        "feeds": (
            "Service inventory and dependency graph context (modules, edges, layering). "
            "Issues include coupling, cycles, dependency direction, and structural risks inferred from the graph."
        ),
        "steps": [
            "Same aggregation as other categories: each architecture finding is one item with severity and impact_score.",
            "category_score = sum(severity_weight × impact_score) / (item_count × 10) × 100, capped at 100.",
        ],
        "no_issues": (
            "With no issues, a provisional score may reflect confidence that services and dependency data were available."
        ),
    },
    "dependency": {
        "feeds": (
            "Static dependency manifests (e.g. requirements.txt, package.json, pyproject.toml) and known "
            "vulnerability or pinning problems (unpinned, wildcard, or advisory-linked versions)."
        ),
        "steps": [
            "Each manifest or dependency-level finding is one item; severity and impact drive the same weighted sum.",
            "category_score = sum(severity_weight × impact_score) / (item_count × 10) × 100, capped at 100.",
        ],
        "no_issues": (
            "With no findings, a small provisional score may reflect medium default coverage for manifest scanning."
        ),
    },
    "documentation": {
        "feeds": (
            "Heuristic checks for repository docs (e.g. README presence) and missing or thin Python docstrings on public APIs."
        ),
        "steps": [
            "Each documentation issue is one item; weighted and normalized like other categories.",
            "category_score = sum(severity_weight × impact_score) / (item_count × 10) × 100, capped at 100.",
        ],
        "no_issues": (
            "If no doc issues are reported, a provisional score may still appear from default coverage confidence."
        ),
    },
    "test_coverage": {
        "feeds": (
            "Heuristic signals from test file layout and optional coverage artifacts (e.g. coverage reports) when present."
        ),
        "steps": [
            "Each test-coverage-related finding is one item; same severity × impact normalization and 0–100 cap.",
        ],
        "no_issues": (
            "With no findings, a small provisional score may reflect that test heuristics ran but did not flag issues."
        ),
    },
    "performance": {
        "feeds": "Performance-related debt items when the analyzers emit them for this category.",
        "steps": [
            "Same formula: weighted sum of items normalized by count × 10, capped at 100.",
        ],
        "no_issues": "Often no provisional score unless coverage metadata is defined for this category.",
    },
    "security": {
        "feeds": "Security-related debt items when classified under this category.",
        "steps": [
            "Same formula: weighted sum of items normalized by count × 10, capped at 100.",
        ],
        "no_issues": "Often 0 when no security items are recorded.",
    },
}


def build_score_explanation() -> Dict[str, Any]:
    return {
        "scale": "0-100",
        "higher_is_worse": True,
        "overall_formula": (
            "overall_score = code_quality*0.30 + architecture*0.25 + "
            "dependency*0.20 + documentation*0.15 + test_coverage*0.10"
        ),
        "category_formula": (
            "category_score = sum(severity_weight * impact_score) / (item_count * 10.0) * 100"
        ),
        "severity_weights": SEVERITY_WEIGHTS,
        "overall_weights": OVERALL_SCORE_WEIGHTS,
        "category_computation": CATEGORY_COMPUTATION,
        "notes": [
            "Each debt item contributes more when its severity and impact score are higher.",
            "Category scores are normalized to a 0-100 scale independently before the weighted overall score is calculated.",
            "Debt density is a separate metric: total debt items divided by estimated KLOC from parsed code elements.",
            "A zero score can still mean low analysis coverage for that category, so always read the category coverage notes too.",
        ],
    }


def build_suggested_fix(item: Dict[str, Any]) -> Dict[str, Any]:
    title = str(item.get("title") or "")
    description = str(item.get("description") or "")
    category = str(item.get("category") or "")
    snippet = str(item.get("code_snippet") or "").strip()
    meta = item.get("meta_data") or item.get("metadata") or {}
    title_lower = title.lower()

    fix = {
        "summary": "Suggested remediation example generated from the debt item metadata.",
        "confidence": "heuristic",
        "before_code": snippet or "",
        "after_code": "",
        "notes": [],
    }

    if category == "dependency" and "unpinned dependency" in title_lower:
        package = str(meta.get("package") or "package_name")
        version = str(meta.get("version") or "x.y.z")
        fix["summary"] = "Pin the dependency to an exact reviewed version."
        fix["after_code"] = f"{package}=={version}"
        fix["notes"] = [
            "Replace floating ranges such as >=, <=, ~=, latest, or * with an exact version after validating compatibility.",
        ]
        return fix

    if category == "dependency" and "wildcard version" in title_lower:
        package = str(meta.get("package") or "package-name")
        fix["summary"] = "Replace wildcard or latest versions with a reviewed semver range or exact version."
        fix["after_code"] = f'"{package}": "^x.y.z"'
        fix["notes"] = [
            "Prefer a tested semver range or exact pin instead of `*` or `latest`.",
        ]
        return fix

    if category == "dependency" and "vulnerable dependency" in title_lower:
        package = str(meta.get("package") or "package_name")
        current = str(meta.get("version") or "current_version")
        fix["summary"] = "Upgrade the dependency to a patched version and verify downstream compatibility."
        fix["after_code"] = f"{package}==<patched-version>"
        fix["notes"] = [
            f"Current detected version: {current}. Replace it with a version confirmed to fix the advisory.",
        ]
        return fix

    if "magic number detected" in title_lower:
        numbers = re.findall(r"\b(?:[0-9]{1,}|[0-9]+\.[0-9]+)\b", snippet)
        value = numbers[0] if numbers else "VALUE"
        fix["summary"] = "Extract the magic value into a named constant so its purpose is explicit."
        fix["after_code"] = (
            f"TIMEOUT_MS = {value}\n"
            "# ...\n"
            f"result = run_task(timeout=TIMEOUT_MS)"
        )
        fix["notes"] = [
            "Choose a constant name that matches the business meaning of the value.",
        ]
        return fix

    if "commented-out code detected" in title_lower:
        fix["summary"] = "Delete dead commented-out code and keep version history in Git instead."
        fix["after_code"] = "# Removed stale commented-out block.\nactive_code_path()"
        fix["notes"] = [
            "If the logic is still needed, reintroduce it as active tested code rather than leaving it commented out.",
        ]
        return fix

    if "long function" in title_lower or "long method" in title_lower:
        fix["summary"] = "Split long routines into smaller helpers with single responsibilities."
        fix["after_code"] = (
            "def process_request(payload):\n"
            "    validated = validate_payload(payload)\n"
            "    transformed = transform_payload(validated)\n"
            "    return persist_payload(transformed)\n\n"
            "def validate_payload(payload):\n"
            "    ...\n\n"
            "def transform_payload(payload):\n"
            "    ...\n\n"
            "def persist_payload(payload):\n"
            "    ..."
        )
        fix["notes"] = [
            "Preserve behavior by extracting cohesive blocks into well-named helpers before changing logic.",
        ]
        return fix

    if "large class" in title_lower:
        fix["summary"] = "Break the large class into smaller collaborators and keep an orchestration layer only where needed."
        fix["after_code"] = (
            "class OrderValidator:\n"
            "    ...\n\n"
            "class OrderPricingService:\n"
            "    ...\n\n"
            "class OrderService:\n"
            "    def __init__(self, validator, pricing_service):\n"
            "        self.validator = validator\n"
            "        self.pricing_service = pricing_service"
        )
        fix["notes"] = [
            "Move validation, persistence, formatting, or integration logic into separate classes or modules.",
        ]
        return fix

    if category == "documentation" and "missing module docstring" in title_lower:
        fix["summary"] = "Add a top-level module docstring that explains the purpose of the file."
        fix["after_code"] = (
            '"""Short summary of this module.\n\n'
            "Explain the main responsibility, key public APIs, and important usage notes.\n"
            '"""'
        )
        return fix

    if category == "documentation" and "undocumented public api" in title_lower:
        fix["summary"] = "Add docstrings to public functions and classes so callers understand behavior and inputs."
        fix["after_code"] = (
            "def public_function(arg1: str, arg2: int) -> bool:\n"
            '    """Explain what this function does.\n\n'
            "    Args:\n"
            "        arg1: Meaning of the first parameter.\n"
            "        arg2: Meaning of the second parameter.\n\n"
            "    Returns:\n"
            "        What the caller should expect back.\n"
            '    """\n'
            "    ..."
        )
        return fix

    if category == "documentation" and "missing repository readme" in title_lower:
        fix["summary"] = "Add a root README that explains setup, usage, and repository structure."
        fix["after_code"] = (
            "# Project Name\n\n"
            "## What this project does\n\n"
            "## How to run it\n\n"
            "## Key modules\n\n"
            "## Development notes\n"
        )
        return fix

    fix["summary"] = "Suggested remediation template based on the debt type."
    fix["after_code"] = (
        "# Remediation template\n"
        "# 1. Isolate the risky logic.\n"
        "# 2. Refactor to a clearer structure.\n"
        "# 3. Add or update tests.\n"
    )
    fix["notes"] = [description] if description else []
    return fix
