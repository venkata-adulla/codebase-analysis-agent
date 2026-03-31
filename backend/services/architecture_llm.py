"""LLM enrichment for architecture reports (executive summaries)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

from openai import OpenAI

from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _client() -> Optional[OpenAI]:
    if not settings.openai_api_key:
        return None
    try:
        return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url or None)
    except Exception as exc:
        logger.warning("architecture_llm: OpenAI init failed: %s", exc)
        return None


def enrich_architecture_narrative(static_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Produce short narrative fields from static analysis JSON.
    Falls back to template text when OPENAI_API_KEY is unset.
    """
    client = _client()
    stack = static_payload.get("technology_stack") or {}
    style = static_payload.get("coding_style") or {}
    risks_block = static_payload.get("risks_and_practices") or {}

    items = stack.get("items") or []
    fe = [i["name"] for i in items if i.get("category") == "frontend"]
    be = [i["name"] for i in items if i.get("category") == "backend"]
    db = [i["name"] for i in items if i.get("category") == "database"]
    other = [i["name"] for i in items if i.get("category") == "other"]

    if not client:
        return _fallback_narrative(static_payload, fe, be, db, other, style, risks_block)

    repo_ctx = static_payload.get("repository_context") or {}
    diagram = static_payload.get("diagram") or {}
    dnodes = diagram.get("nodes") or []

    compact = {
        "repository_folder": repo_ctx.get("folder_name"),
        "readme_excerpt": (repo_ctx.get("readme_excerpt") or "")[:1500],
        "top_level_directories": (repo_ctx.get("top_level_directories") or [])[:20],
        "build_files": repo_ctx.get("build_files") or [],
        "java_sources_hint": repo_ctx.get("java_sources_hint") or "",
        "logical_diagram": [{"label": n.get("label"), "sublabel": n.get("sublabel")} for n in dnodes[:8]],
        "frontend": fe[:8],
        "backend": be[:8],
        "database": db[:8],
        "other": other[:8],
        "coding_style_metrics": {
            "label": style.get("label"),
            "class_ratio": style.get("class_ratio"),
            "avg_function_lines": style.get("avg_function_lines_estimate"),
            "modularity": style.get("modularity_hint"),
            "files_sampled": style.get("files_sampled"),
        },
        "risk_count": len(risks_block.get("risks") or []),
        "risks_titles": [r.get("title") for r in (risks_block.get("risks") or [])[:8]],
        "good": (risks_block.get("best_practices_observed") or [])[:6],
        "missing": (risks_block.get("best_practices_missing") or [])[:6],
    }

    prompt = (
        "You are a senior software architect. Given ONLY the structured facts below, write helpful narratives "
        "for developers. Use the README excerpt and folder names only to describe what the repository appears to be "
        "about when they clearly indicate a product or domain (e.g. pet clinic, e-commerce); otherwise stay generic. "
        "Do not invent specific frameworks, file paths, or microservices not listed in the facts. "
        "Respond with a single JSON object with keys: "
        "architecture_summary (string, 4-7 sentences: purpose/context if README supports it, stack, data layer, "
        "logical view from diagram labels, and how pieces fit together), "
        "coding_style_summary (string, 2-4 sentences), "
        "risks_summary (string, 2-5 sentences mentioning severity themes), "
        "best_practices_summary (string, 2-4 sentences on what looks healthy vs gaps).\n\n"
        f"FACTS:\n{json.dumps(compact, indent=2)}"
    )

    try:
        resp = client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.28,
            max_tokens=1400,
            response_format={"type": "json_object"},
        )
        raw = (resp.choices[0].message.content or "").strip()
        data = json.loads(raw)
        out = {
            "architecture_summary": str(data.get("architecture_summary") or "").strip(),
            "coding_style_summary": str(data.get("coding_style_summary") or "").strip(),
            "risks_summary": str(data.get("risks_summary") or "").strip(),
            "best_practices_summary": str(data.get("best_practices_summary") or "").strip(),
        }
        logger.info("architecture_llm: generated narrative keys=%s", list(out.keys()))
        return out
    except Exception as exc:
        logger.warning("architecture_llm: LLM failed, using fallback: %s", exc)
        return _fallback_narrative(static_payload, fe, be, db, other, style, risks_block)


def _fallback_narrative(
    static_payload: Dict[str, Any],
    fe: list,
    be: list,
    db: list,
    other: list,
    style: Dict[str, Any],
    risks_block: Dict[str, Any],
) -> Dict[str, str]:
    arch = []
    ctx = static_payload.get("repository_context") or {}
    folder = ctx.get("folder_name") or ""
    readme = (ctx.get("readme_excerpt") or "").strip()
    if folder and not re.fullmatch(r"[0-9a-fA-F-]{16,}", str(folder)):
        arch.append(f"This repository appears to be organized under the **{folder}** project folder.")
    if readme:
        readme_lines = [ln.strip() for ln in readme.splitlines() if ln.strip()]
        lead = ""
        for ln in readme_lines[:14]:
            if ln.startswith("<!--"):
                continue
            if ln.startswith("!["):
                continue
            if re.match(r"^<[^>]+>$", ln):
                continue
            lead = ln
            break
        if lead:
            lead = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", lead)
            lead = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", lead)
            lead = re.sub(r"<[^>]+>", " ", lead)
            lead = lead.lstrip("#").strip()
            lead = re.sub(r"\s+", " ", lead)
            lead = lead[:180]
            if lead:
                arch.append(f"Project context from README suggests: {lead}.")
    if fe:
        arch.append(f"Frontend technologies detected include {', '.join(fe[:5])}.")
    if be:
        arch.append(f"Backend stack includes {', '.join(be[:5])}.")
    if db:
        arch.append(f"Data layer signals include {', '.join(db[:4])}.")
    if other:
        arch.append(f"Additional infrastructure: {', '.join(other[:5])}.")
    if not arch:
        arch.append("Limited manifest signals were detected; run a full repository analysis for richer architecture evidence.")

    arch.append(
        "Overall, this is a layered application view inferred from manifests and source layout rather than runtime tracing."
    )

    style_txt = (
        f"Static sampling suggests a {style.get('label', 'mixed')} profile "
        f"(estimated class ratio {style.get('class_ratio', 0):.2f}, "
        f"~{style.get('avg_function_lines_estimate', 0)} lines per function on average)."
    )

    risks = risks_block.get("risks") or []
    risk_txt = (
        f"{len(risks)} risk item(s) flagged from structure and graph heuristics."
        if risks
        else "No major structural risks surfaced by automated heuristics."
    )

    good = risks_block.get("best_practices_observed") or []
    miss = risks_block.get("best_practices_missing") or []
    bp = []
    if good:
        bp.append("Observed: " + "; ".join(good[:3]))
    if miss:
        bp.append("Gaps: " + "; ".join(miss[:3]))

    return {
        "architecture_summary": " ".join(arch),
        "coding_style_summary": style_txt,
        "risks_summary": risk_txt,
        "best_practices_summary": " ".join(bp) if bp else "Review manifests and tests for stronger engineering signals.",
    }
