import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from agents.base_agent import BaseAgent, AgentState
from openai import OpenAI
from core.config import get_settings
from services.openai_chat import chat_completions_create, chat_model_candidates

logger = logging.getLogger(__name__)
settings = get_settings()


def _norm_path(s: str) -> str:
    return (s or "").replace("\\", "/").lower()


def _rel_path_under_repo(repo_root: Path, path_str: str) -> Optional[str]:
    """Return POSIX path relative to repo root, lowercased, or None if outside / invalid."""
    try:
        p = Path(path_str)
        root = repo_root.resolve()
        if p.is_absolute():
            abs_p = p.resolve()
        else:
            abs_p = (root / p).resolve()
        rel = abs_p.relative_to(root)
        out = rel.as_posix().lower()
        return "" if out == "." else out
    except Exception:
        return None


def _service_rel_prefix(service_raw: str, repo_root: Path) -> Optional[str]:
    """
    Directory or package prefix for matching files, relative to repo root.
    ``api/__init__.py`` → ``api``; ``api`` folder → ``api``.
    """
    if not service_raw.strip():
        return None
    root = repo_root.resolve()

    def _from_abs(abs_p: Path) -> Optional[str]:
        try:
            rel = abs_p.relative_to(root)
        except ValueError:
            return None
        rp = rel.as_posix()
        if rp == ".":
            rp = ""
        if rp.endswith("__init__.py"):
            parent = Path(rp).parent
            rp = parent.as_posix() if str(parent) not in (".", "") else ""
        return rp.lower() if rp else ""

    try:
        p = Path(service_raw.replace("\\", "/"))
        if p.is_absolute():
            abs_p = p.resolve()
        else:
            abs_p = (root / p).resolve()
        out = _from_abs(abs_p)
        if out is not None:
            return out
    except Exception:
        pass
    # Stored path pointed at another clone folder — match top-level name if present
    tail = Path(service_raw.replace("\\", "/")).name
    if tail and (root / tail).exists():
        return _from_abs((root / tail).resolve())
    return None


def _path_matches_service(rel_el: str, prefix: str) -> bool:
    if prefix == "":
        return True
    return rel_el == prefix or rel_el.startswith(prefix + "/")


def elements_for_service(
    service: Dict[str, Any],
    code_elements: List[Dict[str, Any]],
    repository_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Map parsed symbols to a service.

    Services backed by ``__init__.py`` represent a whole Python package; include
    symbols from every file under that package directory (not only the init file).
    Single-file services keep exact file matching.

    When ``repository_path`` is set, paths are compared relative to the repo root so
    absolute paths from different clones still align with ``code_elements``.
    """
    raw = (service.get("path") or service.get("file_path") or "").strip()
    if not raw:
        return []

    repo_root: Optional[Path] = None
    if repository_path:
        try:
            repo_root = Path(repository_path).resolve()
        except Exception:
            repo_root = None

    if repo_root and repo_root.is_dir():
        rel_prefix = _service_rel_prefix(raw, repo_root)
        if rel_prefix is not None:
            collected: List[Dict[str, Any]] = []
            for e in code_elements:
                fp = (e.get("file_path") or "").strip()
                if not fp:
                    continue
                rel_el = _rel_path_under_repo(repo_root, fp)
                if rel_el is None:
                    continue
                if _path_matches_service(rel_el, rel_prefix):
                    collected.append(e)
            if collected:
                return collected

    # Fallback: legacy string prefix match (works when repo-relative match failed)
    nraw = _norm_path(raw)
    collected: List[Dict[str, Any]] = []
    pkg_root: Optional[str] = None
    if nraw.endswith("/__init__.py") or nraw.endswith("__init__.py"):
        pr = raw.replace("\\", "/")
        if pr.endswith("__init__.py"):
            pr = pr[: -len("__init__.py")].rstrip("/")
        pkg_root = pr or None
    if pkg_root is not None:
        pkg_prefix = _norm_path(pkg_root + "/")
        for e in code_elements:
            fp = (e.get("file_path") or "").strip()
            if not fp:
                continue
            fn = _norm_path(fp)
            if fn == nraw or fn.startswith(pkg_prefix):
                collected.append(e)
        return collected
    prefix = nraw if nraw.endswith("/") else nraw + "/"
    for e in code_elements:
        fp = (e.get("file_path") or "").strip()
        if not fp:
            continue
        fn = _norm_path(fp)
        if fn == nraw or fn.startswith(prefix):
            collected.append(e)
    return collected


def _resolve_service_path_on_disk(repository_path: str, raw: str) -> Optional[Path]:
    """Map stored service path to a path under the current clone (handles UUID folder changes)."""
    root = Path(repository_path).resolve()
    if not raw.strip():
        return None
    p = Path(raw.replace("\\", "/"))
    if p.is_absolute():
        try:
            rel = p.resolve().relative_to(root)
            cand = (root / rel).resolve()
            if cand.exists():
                return cand
        except ValueError:
            pass
        tail = p.name
        if tail and (root / tail).exists():
            return (root / tail).resolve()
        return None
    cand = (root / p).resolve()
    return cand if cand.exists() else None


def _parse_symbols_under_service(
    service: Dict[str, Any],
    repository_path: str,
    *,
    max_files: int = 160,
) -> List[Dict[str, Any]]:
    """
    When no code_elements matched (e.g. code_browser capped at N files before reaching
    this folder), parse files under the service path directly.
    """
    from services.code_parser import CodeParserService

    raw = (service.get("path") or service.get("file_path") or "").strip()
    if not raw:
        return []
    sp = _resolve_service_path_on_disk(repository_path, raw)
    if sp is None:
        logger.warning("documentation: could not resolve service path %r under %s", raw, repository_path)
        return []

    parser = CodeParserService()
    files: List[Path] = []
    ignore = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".next"}
    if sp.is_dir():
        for ext in ("py", "js", "jsx", "ts", "tsx", "java"):
            for fp in sp.rglob(f"*.{ext}"):
                if fp.is_file() and not any(p in ignore for p in fp.parts):
                    files.append(fp)
        files = sorted(set(files))[:max_files]
    elif sp.is_file():
        files = [sp]

    out: List[Dict[str, Any]] = []
    for fp in files:
        try:
            els = parser.parse_file(str(fp))
            out.extend([e.to_dict() for e in els])
        except Exception as exc:
            logger.debug("documentation parse fallback %s: %s", fp, exc)
    if out:
        logger.info(
            "documentation: fallback-parsed %d symbols from %d file(s) for service %s",
            len(out),
            len(files),
            service.get("name"),
        )
    return out


def _read_pyproject_hint(repository_path: Optional[str], max_chars: int = 900) -> str:
    """First line of [project] description from pyproject.toml for repo-level context."""
    if not repository_path:
        return ""
    try:
        root = Path(repository_path)
        pp = root / "pyproject.toml"
        if not pp.is_file():
            src = root / "src" / "pyproject.toml"
            if src.is_file():
                pp = src
            else:
                return ""
        text = pp.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    m = re.search(
        r"description\s*=\s*[\"']([^\"']+)[\"']",
        text,
        re.IGNORECASE | re.MULTILINE,
    )
    if m:
        return (m.group(1) or "").strip()[:max_chars]
    return ""


def _sibling_service_names(service: Dict[str, Any], all_services: List[Dict[str, Any]], limit: int = 12) -> List[str]:
    """Other module names that share the same top-level package prefix (e.g. click.*)."""
    name = str(service.get("name") or "").strip()
    if "." not in name:
        return []
    prefix = name.split(".")[0] + "."
    out: List[str] = []
    for s in all_services:
        n = str(s.get("name") or "")
        if n and n != name and n.startswith(prefix) and n not in out:
            out.append(n)
        if len(out) >= limit:
            break
    return out


def _display_service_title(name: str) -> str:
    """Readable title fragment for «Foo Bar» Service Documentation."""
    n = (name or "Service").strip()
    if not n:
        n = "Service"
    return n.replace("_", " ")


def _effective_source_file_count(
    service: Dict[str, Any], service_elements: List[Dict[str, Any]]
) -> int:
    """
    Count distinct files from parsed symbols; if extraction is empty but the service
    points at a single source file, treat as 1 so copy does not say «0 files».
    """
    paths = {
        str(e.get("file_path") or "")
        for e in service_elements
        if (e.get("file_path") or "").strip()
    }
    n = len(paths)
    if n > 0:
        return n
    raw = (service.get("path") or service.get("file_path") or "").strip().replace("\\", "/")
    if raw and not raw.endswith("/"):
        lower = raw.lower()
        if any(
            lower.endswith(ext)
            for ext in (
                ".py",
                ".pyi",
                ".js",
                ".jsx",
                ".ts",
                ".tsx",
                ".java",
                ".go",
                ".rs",
                ".rb",
                ".php",
                ".cs",
            )
        ):
            return 1
    return 0


def _structural_doc_bundle(
    service: Dict[str, Any],
    service_elements: List[Dict[str, Any]],
    dependencies: List[Dict[str, Any]],
    *,
    note: str,
    source: str,
) -> Dict[str, Any]:
    """Structural summary + markdown when LLM is skipped; *service_elements* should come from gather."""
    return {
        "description": _build_structural_description(service, service_elements, dependencies),
        "summary": _normalize_inventory_summary(
            _build_structural_summary(service, service_elements, dependencies)
        ),
        "language": service.get("language", "unknown"),
        "note": note,
        "source": source,
    }


def _build_structural_description(
    service: Dict[str, Any],
    service_elements: List[Dict[str, Any]],
    dependencies: List[Dict[str, Any]],
) -> str:
    """Build markdown in the same numbered layout as LLM output (no LLM required)."""
    name = service.get("name", "Service")
    display = _display_service_title(str(name))
    language = (service.get("language") or "unknown").strip()
    path = service.get("path") or ""
    classification = str(service.get("classification") or "").replace("_", " ").strip()
    module_name = str(service.get("module_name") or "").strip()
    entry_points: List[Any] = service.get("entry_points") or []
    entry_point_count = int(service.get("entry_point_count") or len(entry_points) or 0)

    classes = [e for e in service_elements if e.get("type") == "class"]
    functions = [
        e for e in service_elements
        if e.get("type") in ("function", "method")
        and not (e.get("name") or "").startswith("_")
    ]
    private_fns = [
        e for e in service_elements
        if e.get("type") in ("function", "method")
        and (e.get("name") or "").startswith("_")
        and not (e.get("name") or "").startswith("__")
    ]

    outbound = [d for d in dependencies if d.get("source") == service.get("id")]
    inbound = [d for d in dependencies if d.get("target") == service.get("id")]

    files_count = _effective_source_file_count(service, service_elements)

    lines: List[str] = [
        f"# {display} Service Documentation",
        "",
        "## 1. Description",
        "",
    ]

    desc_bits: List[str] = []
    if classification:
        desc_bits.append(f"This module is classified as **{classification}** in the repository analysis.")
    if language and language != "unknown":
        desc_bits.append(f"It is implemented primarily in **{language}**.")
    if path:
        desc_bits.append(f"Source paths center on `{path}`.")
    if files_count:
        desc_bits.append(f"Static analysis covered **{files_count}** file(s) under this service boundary.")
    if not desc_bits:
        desc_bits.append(
            "This area groups related source files in the dependency graph; re-run analysis if symbols look incomplete."
        )
    lines.append(" ".join(desc_bits))
    lines.append("")

    lines += ["## 2. Main Functionality", ""]
    func_bullets: List[str] = []
    if classes:
        func_bullets.append(f"- Defines **{len(classes)}** public class(es) for domain logic and structure.")
    if functions:
        func_bullets.append(f"- Exposes **{len(functions)}** public function(s) or methods for callers.")
    if entry_point_count > 0:
        func_bullets.append(f"- **{entry_point_count}** entry point(s) were detected (CLI, scripts, or app hooks).")
    if outbound:
        func_bullets.append(f"- Integrates with **{len(outbound)}** other module(s) in the dependency map.")
    if inbound:
        func_bullets.append(f"- Referenced by **{len(inbound)}** inbound edge(s) from other modules.")
    if private_fns:
        func_bullets.append(f"- Includes **{len(private_fns)}** internal helper(s) for implementation detail.")
    if not func_bullets:
        func_bullets.append("- _No detailed behavior could be inferred; see key components below._")
    lines.extend(func_bullets)
    lines.append("")

    lines += ["## 3. Key Components", ""]
    comp_lines: List[str] = []
    for cls in classes[:12]:
        cname = cls.get("name", "")
        docstring = (cls.get("docstring") or "").strip()
        if len(docstring) > 120:
            docshort = docstring[:120] + "…"
        else:
            docshort = docstring
        if docshort:
            comp_lines.append(f"- **{cname}:** {docshort}")
        else:
            comp_lines.append(f"- **{cname}:** Class in this module (no docstring extracted).")
    for fn in functions[:12]:
        fname = fn.get("name", "")
        docstring = (fn.get("docstring") or "").strip()
        if len(docstring) > 120:
            docshort = docstring[:120] + "…"
        else:
            docshort = docstring
        label = f"{fname}()"
        if docshort:
            comp_lines.append(f"- **{label}:** {docshort}")
        else:
            comp_lines.append(f"- **{label}:** Public function or method in this module.")
    if len(classes) > 12:
        comp_lines.append(f"- _… and {len(classes) - 12} more class(es)._")
    if len(functions) > 12:
        comp_lines.append(f"- _… and {len(functions) - 12} more function(s)._")
    if not comp_lines and private_fns:
        comp_lines.append(
            f"- _This module exposes little or no public API in static analysis; **{len(private_fns)}** internal "
            "symbol(s) (often compatibility, platform, or underscore helpers) were found—typical for `_compat`-style modules._"
        )
    if not comp_lines:
        comp_lines.append("- _No public classes or functions were extracted; the package may be a thin shim or needs a fresh analysis run._")
    lines.extend(comp_lines)
    lines.append("")

    lines += ["## 4. Dependencies", ""]
    if outbound:
        targets = list({d.get("target_name") or d.get("target") or "" for d in outbound if d.get("target_name") or d.get("target")})[:12]
        for t in targets:
            lines.append(f"- **{t}** — referenced as an outbound dependency in the analysis graph.")
    else:
        lines.append("- _No outbound module dependencies were recorded for this service._")
    lines.append("")

    lines += ["## 5. API Endpoints", ""]
    route_like = [
        f for f in functions
        if any(
            x in (f.get("name") or "").lower()
            for x in ("route", "handler", "endpoint", "view", "get_", "post_", "put_", "delete_")
        )
    ]
    if entry_points:
        if isinstance(entry_points[0], str):
            ep_iter = entry_points
        else:
            ep_iter = [e.get("name", "") for e in entry_points if isinstance(e, dict)]
        for ep in ep_iter[:8]:
            if ep:
                lines.append(f"- **Entry:** `{ep}`")
    if route_like and not entry_points:
        lines.append("- _Possible HTTP or handler symbols were detected; inspect the listed functions for routing decorators._")
    if not entry_points and not route_like:
        lines.append(
            "_No HTTP API surface or named entry points were identified in the extracted symbols. "
            "If this service exposes a web API, it may use patterns not captured by static analysis._"
        )
    if module_name and module_name != name:
        lines.extend(["", f"_Module name in metadata: `{module_name}`._"])

    return "\n".join(lines).strip()


def _build_structural_summary(
    service: Dict[str, Any],
    service_elements: List[Dict[str, Any]],
    dependencies: List[Dict[str, Any]],
) -> str:
    """Plain-English fallback for inventory cards when the LLM is off or returns no summary (no markdown)."""
    name = service.get("name", "Service")
    language = (service.get("language") or "unknown").strip()
    classification = str(service.get("classification") or "").replace("_", " ").strip()
    path = (service.get("path") or "").strip()

    classes = [e for e in service_elements if e.get("type") == "class"]
    functions = [
        e
        for e in service_elements
        if e.get("type") in ("function", "method")
        and not (e.get("name") or "").startswith("_")
    ]
    sid = str(service.get("id") or "")
    outbound = [d for d in dependencies if str(d.get("source") or "") == sid]
    inbound = [d for d in dependencies if str(d.get("target") or "") == sid]

    files_count = _effective_source_file_count(service, service_elements)
    classes_count = len(classes)
    funcs_count = len(functions)

    sentences: List[str] = []
    role = classification or "general"
    sentences.append(
        f"{name} is a {language} area of the codebase that acts as the {role} layer. "
        f"It helps organize {files_count} source file{'s' if files_count != 1 else ''} worth of logic."
    )

    if classes_count or funcs_count:
        sentences.append(
            f"Static analysis surfaced about {classes_count} public classes and {funcs_count} public functions or methods, "
            f"which suggests where callers are likely to hook in."
        )
    else:
        sentences.append(
            "Very few public symbols were extracted here; it may be a thin entry, shim, or re-export module."
        )

    if outbound and inbound:
        sentences.append(
            f"In the dependency map it links outward to other modules in {len(outbound)} place(s) "
            f"and is referenced inward {len(inbound)} time(s), so it sits in the middle of some real wiring."
        )
    elif outbound:
        sentences.append(
            f"It depends on {len(outbound)} mapped link(s) to other parts of the system—worth following when tracing behavior."
        )
    elif inbound:
        sentences.append(
            f"Other modules refer to it in {len(inbound)} place(s), so changes here may have a noticeable ripple."
        )
    else:
        sentences.append(
            "No strong dependency edges were recorded yet, so treat coupling as unknown until the graph fills in."
        )

    if path:
        sentences.append(f"The primary path analyzed was {path}.")

    out = " ".join(sentences).strip()
    return out[:4000] if out else f"{name} ({language}) — summary not yet available."


def _parse_doc_json_payload(raw: str) -> Tuple[str, str]:
    """Parse LLM JSON output into (summary, documentation_markdown). Falls back to raw as doc only."""
    raw = (raw or "").strip()
    if not raw:
        return "", ""
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            summary = (data.get("summary") or "").strip()
            doc = (
                data.get("documentation_markdown")
                or data.get("documentation")
                or data.get("description")
                or ""
            ).strip()
            return summary, doc
    except json.JSONDecodeError:
        pass
    brace = re.search(r"\{[\s\S]*\}", raw)
    if brace:
        try:
            data = json.loads(brace.group(0))
            if isinstance(data, dict):
                summary = (data.get("summary") or "").strip()
                doc = (
                    data.get("documentation_markdown")
                    or data.get("documentation")
                    or data.get("description")
                    or ""
                ).strip()
                return summary, doc
        except json.JSONDecodeError:
            pass
    return "", raw


def _normalize_inventory_summary(text: str) -> str:
    """Card summaries must be plain English only (no markdown artifacts)."""
    if not text or not isinstance(text, str):
        return ""
    t = text.replace("**", "").replace("__", "").strip()
    return t


def gather_service_elements(
    service: Dict[str, Any],
    code_elements: List[Dict[str, Any]],
    repository_path: Optional[str],
) -> List[Dict[str, Any]]:
    """Symbols for one service: global code_elements match, else parse files under service path."""
    el = elements_for_service(service, code_elements, repository_path)
    if not el and repository_path:
        max_files = int(getattr(settings, "documentation_parse_fallback_max_files", 40) or 40)
        el = _parse_symbols_under_service(service, repository_path, max_files=max_files)
    return el


def _documentation_signal_score(
    service: Dict[str, Any],
    service_elements: List[Dict[str, Any]],
    outbound_count: int,
    inbound_count: int,
) -> int:
    """Cheap proxy for whether an LLM call is likely to add value."""
    public_symbols = sum(
        1
        for e in service_elements
        if e.get("type") in ("class", "function", "method")
        and not str(e.get("name") or "").startswith("_")
    )
    entry_points = int(service.get("entry_point_count") or 0)
    classification = str(service.get("classification") or "").strip().lower()
    bonus = 0
    if classification in {"entrypoint", "application_module", "core_library"}:
        bonus += 1
    return public_symbols + entry_points + min(2, outbound_count) + min(2, inbound_count) + bonus


def _llm_priority_score(
    service: Dict[str, Any],
    outbound_count: int,
    inbound_count: int,
) -> int:
    """
    Cheap score to rank services for LLM budgeting before expensive symbol parsing.
    Higher means more likely to benefit from richer LLM docs.
    """
    entry_points = int(service.get("entry_point_count") or 0)
    classification = str(service.get("classification") or "").strip().lower()
    bonus = 0
    if classification in {"entrypoint", "application_module", "core_library"}:
        bonus += 2
    if str(service.get("module_name") or "").strip():
        bonus += 1
    return entry_points + min(3, outbound_count) + min(3, inbound_count) + bonus


class DocumentationAgent(BaseAgent):
    """Agent that generates service documentation using LLM."""

    def __init__(self):
        super().__init__(
            name="documentation_agent",
            description="Generates service documentation using LLM",
        )
        self.client = None
        if settings.openai_api_key:
            try:
                self.client = OpenAI(
                    api_key=settings.openai_api_key,
                    base_url=settings.openai_base_url or None,
                )
            except Exception as exc:
                logger.warning("Could not initialise OpenAI client: %s", exc)

    def execute(self, state: AgentState) -> AgentState:
        """Execute documentation generation."""
        services = state.get("services", [])

        if not services:
            logger.warning("No services found for documentation")
            return state

        logger.info("Documentation agent generating docs for %d services", len(services))
        if settings.openai_api_key:
            doc_model = (getattr(settings, "documentation_model", "") or "").strip()
            cands = chat_model_candidates()
            logger.info(
                "Documentation LLM: doc_model=%s (global primary=%s, fallbacks=%s)",
                doc_model or "(using global)",
                cands[0] if cands else "(unset)",
                cands[1:] if len(cands) > 1 else [],
            )

        code_elements: List[Dict[str, Any]] = state.get("code_elements") or []
        dependencies: List[Dict[str, Any]] = state.get("dependencies") or []

        documentation: Dict[str, Any] = {}
        repository_path = state.get("repository_path")
        pyproject_hint = _read_pyproject_hint(repository_path)

        wall0 = time.perf_counter()
        to_run = [s for s in services if str(s.get("id") or "").strip()]
        dep_out: Dict[str, int] = {}
        dep_in: Dict[str, int] = {}
        for d in dependencies:
            src = str(d.get("source") or "").strip()
            tgt = str(d.get("target") or "").strip()
            if src:
                dep_out[src] = dep_out.get(src, 0) + 1
            if tgt:
                dep_in[tgt] = dep_in.get(tgt, 0) + 1
        max_llm_services = int(getattr(settings, "documentation_max_llm_services", 0) or 0)
        if max_llm_services > 0:
            ranked = sorted(
                to_run,
                key=lambda s: _llm_priority_score(
                    s,
                    dep_out.get(str(s.get("id") or ""), 0),
                    dep_in.get(str(s.get("id") or ""), 0),
                ),
                reverse=True,
            )
            llm_allowed_ids = {
                str(s.get("id") or "").strip()
                for s in ranked[:max_llm_services]
                if str(s.get("id") or "").strip()
            }
        else:
            llm_allowed_ids = {
                str(s.get("id") or "").strip()
                for s in to_run
                if str(s.get("id") or "").strip()
            }
        logger.info(
            "documentation_agent: llm_budget=%d/%d service(s) (cap=%d)",
            len(llm_allowed_ids),
            len(to_run),
            max_llm_services,
        )
        workers_cfg = int(getattr(settings, "documentation_parallel_workers", 6) or 0)
        use_parallel = (
            self.client
            and workers_cfg > 0
            and len(to_run) > 1
        )
        if use_parallel:
            n_workers = min(workers_cfg, len(to_run), 16)
            doc_m = (getattr(settings, "documentation_model", "") or "").strip()
            logger.info(
                "documentation_agent: parallel LLM workers=%d services=%d max_tokens=%d model=%s",
                n_workers,
                len(to_run),
                int(getattr(settings, "documentation_max_tokens", 3200) or 3200),
                doc_m or (settings.openai_model or "").strip() or "(unset)",
            )
            with ThreadPoolExecutor(max_workers=n_workers) as pool:
                futures = {
                    pool.submit(
                        self._document_single_service,
                        svc,
                        code_elements,
                        dependencies,
                        repository_path,
                        services,
                        pyproject_hint,
                        llm_allowed_ids,
                    ): svc
                    for svc in to_run
                }
                for fut in as_completed(futures):
                    sid, doc = fut.result()
                    if sid and doc is not None:
                        documentation[sid] = doc
        else:
            if self.client and len(to_run) > 1 and workers_cfg <= 0:
                logger.info(
                    "documentation_agent: sequential mode (DOCUMENTATION_PARALLEL_WORKERS=0)"
                )
            for service in to_run:
                sid, doc = self._document_single_service(
                    service,
                    code_elements,
                    dependencies,
                    repository_path,
                    services,
                    pyproject_hint,
                    llm_allowed_ids,
                )
                if sid and doc is not None:
                    documentation[sid] = doc

        elapsed = time.perf_counter() - wall0
        state.update("documentation", documentation)

        state.add_history({
            "agent": self.name,
            "action": "generated_documentation",
            "services_documented": len(documentation),
        })

        logger.info(
            "Documentation agent completed: %d services in %.2fs wall time (parallel=%s)",
            len(documentation),
            elapsed,
            use_parallel,
        )
        return state

    def _document_single_service(
        self,
        service: Dict[str, Any],
        code_elements: List[Dict[str, Any]],
        dependencies: List[Dict[str, Any]],
        repository_path: Optional[str],
        all_services: List[Dict[str, Any]],
        pyproject_hint: str,
        llm_allowed_ids: set[str],
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Generate docs for one service; used from main thread or worker thread."""
        sid = str(service.get("id") or "").strip()
        if not sid:
            return "", None
        t0 = time.perf_counter()
        try:
            doc = self._generate_documentation(
                service,
                code_elements,
                dependencies,
                repository_path=repository_path,
                all_services=all_services,
                pyproject_hint=pyproject_hint,
                llm_allowed_ids=llm_allowed_ids,
            )
            logger.info(
                "documentation_agent: service=%r id=%s… done in %.2fs",
                service.get("name"),
                sid[:8],
                time.perf_counter() - t0,
            )
            return sid, doc
        except Exception as exc:
            logger.error("Error generating documentation for %s: %s", service.get("id"), exc)
            service_elements = gather_service_elements(service, code_elements, repository_path)
            structural_desc = _build_structural_description(
                service, service_elements, dependencies
            )
            return sid, {
                "description": structural_desc,
                "summary": _normalize_inventory_summary(
                    _build_structural_summary(
                        service, service_elements, dependencies
                    )
                ),
                "language": service.get("language", "unknown"),
                "error": str(exc),
            }

    def _generate_documentation(
        self,
        service: Dict[str, Any],
        code_elements: List[Dict[str, Any]],
        dependencies: List[Dict[str, Any]],
        *,
        repository_path: Optional[str] = None,
        all_services: Optional[List[Dict[str, Any]]] = None,
        pyproject_hint: str = "",
        llm_allowed_ids: Optional[set[str]] = None,
    ) -> Dict[str, Any]:
        """Generate documentation for a service."""
        svc_id = str(service.get("id") or "")
        outbound = [d for d in dependencies if str(d.get("source") or "") == svc_id]
        inbound = [d for d in dependencies if str(d.get("target") or "") == svc_id]
        min_signal = int(getattr(settings, "documentation_llm_min_signal", 4) or 4)
        if not self.client:
            logger.info(
                "Documentation (no LLM) for %s: structural path with symbol gather",
                service.get("name"),
            )
            els = gather_service_elements(service, code_elements, repository_path)
            return _structural_doc_bundle(
                service,
                els,
                dependencies,
                note="OpenAI API key not configured — showing structural analysis",
                source="structural",
            )
        if llm_allowed_ids is not None and svc_id not in llm_allowed_ids:
            logger.info(
                "Documentation budget fast-path for %s: outside LLM budget; structural docs with symbol gather",
                service.get("name"),
            )
            els = gather_service_elements(service, code_elements, repository_path)
            return _structural_doc_bundle(
                service,
                els,
                dependencies,
                note="Used structural documentation fast-path (outside LLM budget)",
                source="structural_budget_fast_path",
            )
        cheap_signal = _llm_priority_score(service, len(outbound), len(inbound))
        if cheap_signal < min_signal:
            logger.info(
                "Documentation fast-path for %s: cheap_signal=%d < min_signal=%d; structural docs with symbol gather",
                service.get("name"),
                cheap_signal,
                min_signal,
            )
            els = gather_service_elements(service, code_elements, repository_path)
            return _structural_doc_bundle(
                service,
                els,
                dependencies,
                note=f"Used structural documentation fast-path (cheap_signal={cheap_signal})",
                source="structural_cheap_signal_fast_path",
            )

        service_elements = gather_service_elements(service, code_elements, repository_path)
        structural_desc = _build_structural_description(service, service_elements, dependencies)
        struct_summary = _build_structural_summary(service, service_elements, dependencies)
        llm_signal = _documentation_signal_score(service, service_elements, len(outbound), len(inbound))
        if llm_signal < min_signal:
            logger.info(
                "Documentation fast-path for %s: signal=%d < min_signal=%d; using structural docs",
                service.get("name"),
                llm_signal,
                min_signal,
            )
            return {
                "description": structural_desc,
                "summary": _normalize_inventory_summary(struct_summary),
                "language": service.get("language", "unknown"),
                "note": f"Used structural documentation fast-path (signal={llm_signal})",
                "source": "structural_fast_path",
            }

        # Build the LLM prompt — include package-wide symbols when path is __init__.py
        element_lines: List[str] = []
        by_file: Dict[str, int] = {}
        for e in service_elements[:32]:
            fp = (e.get("file_path") or "").replace("\\", "/").split("/")[-1]
            by_file[fp] = by_file.get(fp, 0) + 1
            etype = e.get("type", "")
            ename = e.get("name", "")
            edoc = (e.get("docstring") or "").strip()[:140]
            element_lines.append(f"  - {etype} `{ename}` ({fp})" + (f": {edoc}" if edoc else ""))
        elements_block = "\n".join(element_lines) if element_lines else "  (no elements extracted)"
        file_summary = ", ".join(f"{k} ({v} symbols)" for k, v in sorted(by_file.items())[:12])
        dep_names = list({d.get("target_name") or d.get("target") or "" for d in outbound if d.get("target_name") or d.get("target")})[:10]
        used_by = len(inbound)

        repo_label = ""
        try:
            if repository_path:
                repo_label = Path(repository_path).name
        except Exception:
            repo_label = ""
        siblings = _sibling_service_names(service, all_services or [], limit=14)
        sibling_line = ", ".join(siblings) if siblings else "(none listed)"

        unique_paths = {
            str(e.get("file_path") or "")
            for e in service_elements
            if (e.get("file_path") or "").strip()
        }
        files_count = len(unique_paths)

        repo_ctx = ""
        if pyproject_hint:
            repo_ctx = f"\nRepository one-liner (from pyproject): {pyproject_hint}\n"

        prompt = (
            f"You are documenting a module in the repository «{repo_label or 'this codebase'}».\n\n"
            f"## Module name: {service['name']}\n"
            f"- Language: {service.get('language', 'unknown')}\n"
            f"- Role tag (heuristic): {service.get('classification') or 'unknown'}\n"
            f"- Primary path: {service.get('path', '')}\n"
            f"- Entry points: {service.get('entry_point_count', 0)}\n"
            f"- Outbound deps (other modules): {', '.join(dep_names) if dep_names else 'none listed'}\n"
            f"- Inbound references in graph: {used_by}\n"
            f"- Neighbor modules: {sibling_line}\n"
            f"- Files with symbols: {file_summary or 'n/a'}\n"
            f"{repo_ctx}\n"
            "### Extracted symbols (sample; package roots may include many files)\n"
            f"{elements_block}\n\n"
            "### Quick facts (do not copy wording; infer purpose from symbols and paths)\n"
            f"- About {len(service_elements)} symbol(s) sampled; spans {files_count} distinct file(s) in this module.\n"
            f"- Dependency edges: {len(outbound)} outward, {len(inbound)} inward.\n\n"
            "Respond with JSON only (no markdown fences) and exactly these keys:\n"
            '- "summary": string. Plain English only: no markdown, no **, no headings, no bullet characters. '
            "Write 4–8 sentences as continuous prose. Describe what this module does for the product, "
            "how it fits next to sibling modules, and what a maintainer should verify first. "
            "Do NOT open with «X is a python module classified as» or similar filler.\n"
            '- "documentation_markdown": string. Full Markdown document that MUST follow this outline exactly '
            "(use `#` for the title, `##` for numbered sections, and normal Markdown lists and **bold** labels):\n\n"
            f"# {_display_service_title(str(service.get('name') or 'Service'))} Service Documentation\n\n"
            "## 1. Description\n"
            "One or two paragraphs: purpose, scope, and role in the repository.\n\n"
            "## 2. Main Functionality\n"
            "Bullet list of 4–10 concrete capabilities (what users or other code get from this module).\n\n"
            "## 3. Key Components\n"
            "Bullet list. Each line: **ComponentName** — short explanation (classes, key functions, or submodules). "
            "Prefer names from the extracted symbols above.\n\n"
            "## 4. Dependencies\n"
            "Bullet list. Each line: **Dependency** — what it is used for (libraries, other services in the graph, or "
            "`none detected` if truly unknown). Do not invent version numbers.\n\n"
            "## 5. API Endpoints\n"
            "If the module exposes HTTP routes, RPC, or CLI commands visible from symbols or paths, document them with "
            "method/path or command, and include fenced ```json code blocks for at least one example request and one "
            "example response where appropriate. "
            "If there is no API surface, write a single paragraph stating that no HTTP/API endpoints were identified "
            "from static analysis (not a bullet list).\n\n"
            "Style: professional internal documentation like the rest of the product. "
            "Ground claims in the symbols and paths given; mark inference clearly when needed.\n"
        )

        try:
            llm_text = self._call_llm_json(prompt)
            if not llm_text:
                raise ValueError("Empty response from OpenAI")
            summary, doc_md = _parse_doc_json_payload(llm_text)
            if not doc_md:
                raise ValueError("JSON response missing documentation_markdown")
            sc = _normalize_inventory_summary((summary or "").strip()[:4000])
            summary_clean: Optional[str] = sc if sc else None
            if not summary_clean:
                summary_clean = _normalize_inventory_summary(struct_summary)
                logger.info(
                    "LLM returned empty summary for %s; using structural summary",
                    service.get("name"),
                )
            logger.info(
                "AI documentation for %s: summary_len=%s doc_len=%s",
                service.get("name"),
                len(summary_clean or ""),
                len(doc_md),
            )
            return {
                "description": doc_md,
                "summary": summary_clean,
                "language": service.get("language", "unknown"),
                "elements_count": len(service_elements),
                "source": "llm",
            }
        except Exception as exc:
            logger.warning("OpenAI call failed for %s (%s), using structural fallback", service["name"], exc)
            return {
                "description": structural_desc,
                "summary": _normalize_inventory_summary(struct_summary),
                "language": service.get("language", "unknown"),
                "error": str(exc),
                "source": "structural",
            }

    def _call_llm_json(self, prompt: str) -> str:
        """Request JSON documentation; retry without json_object if the model/API rejects it."""
        doc_model = (getattr(settings, "documentation_model", "") or "").strip() or None
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a senior software architect. Output a single JSON object only. "
                    "The summary field must be plain English paragraphs for a product engineer: "
                    "concrete and specific. "
                    "The documentation_markdown field must use the numbered section template "
                    "(## 1. Description through ## 5. API Endpoints) with a top-level "
                    "'# … Service Documentation' title, matching internal service docs style. "
                    "Never echo the words 'classified as' or 'package root' unless unavoidable."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        max_tok = int(getattr(settings, "documentation_max_tokens", 3200) or 3200)
        kwargs = {
            "messages": messages,
            "max_tokens": max_tok,
            "temperature": 0.42,
            "timeout": int(getattr(settings, "documentation_llm_timeout_sec", 30) or 30),
        }
        try:
            response = chat_completions_create(
                self.client,
                model_override=doc_model,
                **kwargs,
                response_format={"type": "json_object"},
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as first_exc:
            logger.warning(
                "JSON-mode LLM call failed (%s); retrying without response_format",
                first_exc,
            )
            response = chat_completions_create(self.client, model_override=doc_model, **kwargs)
            return (response.choices[0].message.content or "").strip()
