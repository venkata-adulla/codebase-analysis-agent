import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from agents.base_agent import BaseAgent, AgentState
from openai import OpenAI
from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _norm_path(s: str) -> str:
    return (s or "").replace("\\", "/").lower()


def elements_for_service(
    service: Dict[str, Any], code_elements: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Map parsed symbols to a service.

    Services backed by ``__init__.py`` represent a whole Python package; include
    symbols from every file under that package directory (not only the init file).
    Single-file services keep exact file matching.
    """
    raw = (service.get("path") or "").strip()
    if not raw:
        return []
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
    else:
        # Single file, or a directory-style service path (discovered clusters)
        prefix = nraw if nraw.endswith("/") else nraw + "/"
        for e in code_elements:
            fp = (e.get("file_path") or "").strip()
            if not fp:
                continue
            fn = _norm_path(fp)
            if fn == nraw or fn.startswith(prefix):
                collected.append(e)
    return collected


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


def _build_structural_description(
    service: Dict[str, Any],
    service_elements: List[Dict[str, Any]],
    dependencies: List[Dict[str, Any]],
) -> str:
    """Build a rich markdown description purely from analysis data (no LLM required)."""
    name = service.get("name", "Service")
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

    # Imports from this service to other services
    outbound = [d for d in dependencies if d.get("source") == service.get("id")]
    inbound = [d for d in dependencies if d.get("target") == service.get("id")]

    # Avoid repeating the module name as a heading — inventory UI already shows it as the title.
    lines: List[str] = ["#### Module overview", ""]

    if classification:
        lines.append(f"- **Classification:** {classification}")
    if language and language != "unknown":
        lines.append(f"- **Language:** {language}")
    if module_name and module_name != name:
        lines.append(f"- **Module name:** `{module_name}`")
    if path:
        lines.append(f"- **Path:** `{path}`")
    lines.append("")

    if classes:
        lines += ["", f"**Classes ({len(classes)}):**"]
        for cls in classes[:8]:
            cname = cls.get("name", "")
            docstring = (cls.get("docstring") or "").strip()
            suffix = f" — {docstring[:80]}" if docstring else ""
            lines.append(f"- `{cname}`{suffix}")
        if len(classes) > 8:
            lines.append(f"- … and {len(classes) - 8} more")

    if functions:
        lines += ["", f"**Public functions / methods ({len(functions)}):**"]
        for fn in functions[:10]:
            fname = fn.get("name", "")
            docstring = (fn.get("docstring") or "").strip()
            suffix = f" — {docstring[:80]}" if docstring else ""
            lines.append(f"- `{fname}(){suffix}`")
        if len(functions) > 10:
            lines.append(f"- … and {len(functions) - 10} more")

    if private_fns:
        lines += ["", f"**Internal helpers:** {len(private_fns)} private function(s)"]

    if entry_point_count > 0:
        lines += ["", f"**Entry points detected:** {entry_point_count}"]
        if entry_points:
            if isinstance(entry_points[0], str):
                ep_iter = entry_points
            else:
                ep_iter = [e.get("name", "") for e in entry_points if isinstance(e, dict)]
            for ep in ep_iter[:5]:
                if ep:
                    lines.append(f"- `{ep}`")

    if outbound:
        targets = list({d.get("target_name") or d.get("target") or "" for d in outbound if d.get("target_name") or d.get("target")})[:6]
        if targets:
            lines += ["", f"**Depends on:** {', '.join(f'`{t}`' for t in targets)}"]

    if inbound:
        lines += ["", f"**Used by:** {len(inbound)} other module(s)"]

    if not classes and not functions and not outbound and not inbound:
        lines += ["", "_No public symbols detected for this module._"]

    return "\n".join(lines).strip()


def _build_structural_summary(
    service: Dict[str, Any],
    service_elements: List[Dict[str, Any]],
    dependencies: List[Dict[str, Any]],
) -> str:
    """Readable fallback summary for cards when the LLM is off or returns no summary."""
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

    unique_files = {
        str(e.get("file_path") or "")
        for e in service_elements
        if (e.get("file_path") or "").strip()
    }
    files_count = len(unique_files)
    classes_count = len(classes)
    funcs_count = len(functions)






    opening = f"**{name}** is a {language} module"
    if classification:
        opening += f" in the **{classification}** layer"
    opening += "."


    opening = f"**{name}** is a {language} module"
    if classification:
        opening += f" in the **{classification}** layer"
    opening += "."

    if classes_count or funcs_count:
        behavior = (
            f"In plain terms, this part of the codebase currently exposes about **{classes_count} class(es)** "
            f"and **{funcs_count} public method/function entry points**."
        )
    else:
        behavior = "In plain terms, no clear public API surface was detected from the extracted symbols."

    coupling_parts: List[str] = []
    if outbound:
        coupling_parts.append(f"it calls or depends on **{len(outbound)}** other mapped module link(s)")
    if inbound:
        coupling_parts.append(f"it is used by **{len(inbound)}** inbound link(s)")
    coupling = (
        f"From the dependency graph perspective, {', and '.join(coupling_parts)}."
        if coupling_parts
        else "From the current dependency graph snapshot, strong coupling signals were not detected yet."
    )

    details = (
        f"It draws information from **{files_count} source file(s)**"
        + (f", primarily located at `{path}`." if path else ".")
    )

    summary = f"{opening}\n\n{behavior}\n\n{coupling}\n\n{details}".strip()

    details = (
        f"It draws information from **{files_count} source file(s)**"
        + (f", primarily located at `{path}`." if path else ".")
    )

    summary = f"{opening}\n\n{behavior}\n\n{coupling}\n\n{details}".strip()

    details = (
        f"It draws information from **{files_count} source file(s)**"
        + (f", primarily located at `{path}`." if path else ".")
    )

    summary = f"{opening}\n\n{behavior}\n\n{coupling}\n\n{details}".strip()

    summary = f"{opening}\n\n{behavior}\n\n{coupling}\n\n{details}".strip()

    details = (
        f"It draws information from **{files_count} source file(s)**"
        + (f", primarily located at `{path}`." if path else ".")
    )

    summary = f"{opening}\n\n{behavior}\n\n{coupling}\n\n{details}".strip()

    summary = f"{opening}\n\n{behavior}\n\n{coupling}\n\n{details}".strip()

    summary = f"{opening}\n\n{behavior}\n\n{coupling}\n\n{details}".strip()

    summary = f"{opening}\n\n{behavior}\n\n{coupling}\n\n{details}".strip()

    details = (
        f"It draws information from **{files_count} source file(s)**"
        + (f", primarily located at `{path}`." if path else ".")
    )

    summary = f"{opening}\n\n{behavior}\n\n{coupling}\n\n{details}".strip()

    opening = (
        f"**{name}** is a **{language}** module"
        + (f" classified as **{classification}**" if classification else "")
        + "."
    )

    if classes_count or funcs_count:
        behavior = (
            f"It appears to define the core behavior through **{classes_count} class(es)** "
            f"and **{funcs_count} public function(s)/method(s)**."
        )
    else:
        behavior = "No public classes or functions were detected in the extracted symbols."

    coupling_parts: List[str] = []
    if outbound:
        coupling_parts.append(f"depends on **{len(outbound)}** mapped dependency link(s)")
    if inbound:
        coupling_parts.append(f"is referenced by **{len(inbound)}** inbound link(s)")
    coupling = (
        f"In this repository graph, it {', and '.join(coupling_parts)}."
        if coupling_parts
        else "In this repository graph, no strong coupling signals were detected yet."
    )

    bullets: List[str] = []
    bullets.append(f"- Language: **{language}**")
    if classification:
        bullets.append(f"- Module type: **{classification}**")
    bullets.append(f"- Files contributing symbols: **{files_count}**")
    bullets.append(f"- Public API surface: **{classes_count} classes**, **{funcs_count} methods/functions**")
    if path:
        bullets.append(f"- Source location: `{path}`")

    summary = (
        f"{opening}\n\n"
        f"{behavior}\n\n"
        f"{coupling}\n\n"
        "### At a glance\n"
        + "\n".join(bullets)
    ).strip()
    return summary[:4000] if summary else f"Module {name} ({language})."


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

        code_elements: List[Dict[str, Any]] = state.get("code_elements") or []
        dependencies: List[Dict[str, Any]] = state.get("dependencies") or []

        documentation: Dict[str, Any] = {}
        repository_path = state.get("repository_path")
        pyproject_hint = _read_pyproject_hint(repository_path)

        for service in services:
            sid = str(service.get("id") or "").strip()
            if not sid:
                continue
            try:
                doc = self._generate_documentation(
                    service,
                    code_elements,
                    dependencies,
                    repository_path=repository_path,
                    all_services=services,
                    pyproject_hint=pyproject_hint,
                )
                documentation[sid] = doc
            except Exception as exc:
                logger.error("Error generating documentation for %s: %s", service["id"], exc)
                service_elements = elements_for_service(service, code_elements)
                structural_desc = _build_structural_description(
                    service, service_elements, dependencies
                )
                documentation[sid] = {
                    "description": structural_desc,
                    "summary": _build_structural_summary(
                        service, service_elements, dependencies
                    ),
                    "language": service.get("language", "unknown"),
                    "error": str(exc),
                }

        state.update("documentation", documentation)

        state.add_history({
            "agent": self.name,
            "action": "generated_documentation",
            "services_documented": len(documentation),
        })

        logger.info("Documentation agent completed: %d services documented", len(documentation))
        return state

    def _generate_documentation(
        self,
        service: Dict[str, Any],
        code_elements: List[Dict[str, Any]],
        dependencies: List[Dict[str, Any]],
        *,
        repository_path: Optional[str] = None,
        all_services: Optional[List[Dict[str, Any]]] = None,
        pyproject_hint: str = "",
    ) -> Dict[str, Any]:
        """Generate documentation for a service."""
        service_elements = elements_for_service(service, code_elements)

        # Always build the structural description first (no LLM needed)
        structural_desc = _build_structural_description(service, service_elements, dependencies)

        struct_summary = _build_structural_summary(
            service, service_elements, dependencies
        )
        if not self.client:
            logger.info(
                "Documentation (no LLM) for %s: structural summary + body",
                service.get("name"),
            )
            return {
                "description": structural_desc,
                "summary": struct_summary,
                "language": service.get("language", "unknown"),
                "note": "OpenAI API key not configured — showing structural analysis",
                "source": "structural",
            }

        # Build the LLM prompt — include package-wide symbols when path is __init__.py
        element_lines: List[str] = []
        by_file: Dict[str, int] = {}
        for e in service_elements[:55]:
            fp = (e.get("file_path") or "").replace("\\", "/").split("/")[-1]
            by_file[fp] = by_file.get(fp, 0) + 1
            etype = e.get("type", "")
            ename = e.get("name", "")
            edoc = (e.get("docstring") or "").strip()[:140]
            element_lines.append(f"  - {etype} `{ename}` ({fp})" + (f": {edoc}" if edoc else ""))
        elements_block = "\n".join(element_lines) if element_lines else "  (no elements extracted)"
        file_summary = ", ".join(f"{k} ({v} symbols)" for k, v in sorted(by_file.items())[:12])

        svc_id = str(service.get("id") or "")
        outbound = [d for d in dependencies if str(d.get("source") or "") == svc_id]
        inbound = [d for d in dependencies if str(d.get("target") or "") == svc_id]
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

        repo_ctx = ""
        if pyproject_hint:
            repo_ctx = f"\n**Repository (pyproject) one-liner:** {pyproject_hint}\n"

        prompt = (
            f"You are documenting a module inside the codebase **{repo_label or 'this repository'}**.\n\n"
            f"## Module: **{service['name']}**\n"
            f"- Language: {service.get('language', 'unknown')}\n"
            f"- Classification: {service.get('classification') or 'unknown'}\n"
            f"- Primary path: {service.get('path', '')}\n"
            f"- Entry points: {service.get('entry_point_count', 0)}\n"
            f"- Depends on (other modules/services): {', '.join(dep_names) if dep_names else 'none listed'}\n"
            f"- Referenced by: {used_by} inbound edge(s) in the dependency graph\n"
            f"- Sibling modules in same package: {sibling_line}\n"
            f"- Source files contributing symbols: {file_summary or 'n/a'}\n"
            f"{repo_ctx}\n"
            "### Extracted symbols (may span multiple files if this is a package)\n"
            f"{elements_block}\n\n"
            "### Structural outline (deterministic; use as facts, expand with prose)\n"
            f"{struct_summary}\n\n"
            "Respond with **JSON only** (no markdown outside the JSON) with exactly these keys:\n"
            '- "summary": string, **plain text, no markdown**. Write **4–8 sentences** in natural language '
            "for a developer who is new to this repo. Explain **what this module is for**, how it fits "
            "into the project, **main responsibilities**, and notable public APIs or patterns. "
            "If the only path is `__init__.py` but sibling files exist, infer the package’s role from "
            "symbols and dependencies — do **not** say “nothing here” unless truly no symbols exist.\n"
            '- "documentation_markdown": string, Markdown body with sections: '
            '"### Overview", "### Responsibilities" (bullets), "### Key symbols" (optional), '
            '"### Dependencies" (brief). Target **250–450 words** when enough context exists.\n'
        )

        try:
            llm_text = self._call_llm_json(prompt)
            if not llm_text:
                raise ValueError("Empty response from OpenAI")
            summary, doc_md = _parse_doc_json_payload(llm_text)
            if not doc_md:
                raise ValueError("JSON response missing documentation_markdown")
            sc = (summary or "").strip()[:4000]
            summary_clean: Optional[str] = sc if sc else None
            if not summary_clean:
                summary_clean = struct_summary
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
                "summary": struct_summary,
                "language": service.get("language", "unknown"),
                "error": str(exc),
                "source": "structural",
            }

    def _call_llm_json(self, prompt: str) -> str:
        """Request JSON documentation; retry without json_object if the model/API rejects it."""
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a senior software architect writing documentation. "
                    "Use clear, precise English. Output valid JSON only. "
                    "The summary must read like a helpful README excerpt, not a template."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        kwargs = {
            "model": settings.openai_model,
            "messages": messages,
            "max_tokens": 2800,
            "temperature": 0.35,
        }
        try:
            response = self.client.chat.completions.create(
                **kwargs,
                response_format={"type": "json_object"},
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as first_exc:
            logger.warning(
                "JSON-mode LLM call failed (%s); retrying without response_format",
                first_exc,
            )
            response = self.client.chat.completions.create(**kwargs)
            return (response.choices[0].message.content or "").strip()
