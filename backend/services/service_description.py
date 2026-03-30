import re
from typing import Any, Dict, Optional

# Bare stub produced when OpenAI was unavailable: "Service: click._compat"
_STUB_RE = re.compile(r"^service:\s*\S+$", re.IGNORECASE)


def is_stub_description(text: object) -> bool:
    """Return True if *text* is empty or is a known bare auto-generated stub."""
    if not isinstance(text, str) or not text.strip():
        return True
    stripped = text.strip()
    if _STUB_RE.match(stripped):
        return True
    # Very short single-line non-markdown lines are stubs too
    if len(stripped) < 40 and "\n" not in stripped and not stripped.startswith("#"):
        return True
    return False


def build_service_summary_plain(
    *,
    service_name: str,
    language: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Short plain-text blurb for inventory cards when no LLM summary exists in the database.
    Keeps copy consistent and readable (not raw markdown).
    """
    meta = metadata or {}
    classification = str(meta.get("classification") or "").replace("_", " ").strip() or "module"
    ep = int(meta.get("entry_point_count") or 0)
    lang = (language or "unknown").strip() or "unknown"
    sym = meta.get("symbol_stats") if isinstance(meta.get("symbol_stats"), dict) else {}
    classes = int(sym.get("class_count") or 0) if sym else 0
    funcs = int(sym.get("function_count") or 0) if sym else 0

    head = f"{service_name} is a {lang} module classified as {classification}."
    if ep > 0:
        return f"{head} It exposes {ep} public entry point(s)."
    if classes or funcs:
        parts = []
        if classes:
            parts.append(f"{classes} class(es)")
        if funcs:
            parts.append(f"{funcs} public function(s) or methods")
        return f"{head} It contains {', and '.join(parts)} in the extracted symbols."
    return f"{head} No public classes or functions were detected in the extracted symbols."


def build_service_description(
    *,
    service_name: str,
    language: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    path: Optional[str] = None,
) -> str:
    """Markdown for UI cards/detail. No H1–H3 title — the inventory header already shows the service name."""
    meta = metadata or {}
    classification = str(meta.get("classification") or "").replace("_", " ").strip()
    module_name = str(meta.get("module_name") or "").strip()
    entry_points = meta.get("entry_points") or []
    entry_point_count = int(meta.get("entry_point_count") or len(entry_points) or 0)
    lang = (language or "unknown").strip() or "unknown"

    lines = [
        "#### Summary",
        "",
        f"- **Language:** {lang}",
    ]
    if classification:
        lines.append(f"- **Module role:** {classification}")
    if module_name and module_name != service_name:
        lines.append(f"- **Import path / name:** `{module_name}`")
    if entry_point_count > 0:
        lines.append(f"- **Entry points:** {entry_point_count}")
    if path:
        lines.append(f"- **Source file:** `{path}`")

    lines.extend(
        [
            "",
            "_Richer prose appears when documentation generation succeeds (valid `OPENAI_MODEL` and API key)._",
            "",
            "Re-run **Analyze** after fixing `.env` if summaries stay minimal.",
        ]
    )
    return "\n".join(lines).strip()
