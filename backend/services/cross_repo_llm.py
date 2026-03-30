"""LLM narrative for cross-repository comparison."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from openai import OpenAI

from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _client():
    if not settings.openai_api_key:
        return None
    try:
        return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url or None)
    except Exception as exc:
        logger.warning("cross_repo_llm: OpenAI init failed: %s", exc)
        return None


def enrich_cross_repo_llm(llm_context: Dict[str, Any]) -> Dict[str, Any]:
    """Returns summary, key_differences, recommendation, full_text (markdown)."""
    client = _client()
    compact = json.dumps(llm_context, indent=2, default=str)[:12000]

    if not client:
        return _fallback(llm_context)

    prompt = (
        "You are a senior software architect comparing multiple repositories. "
        "Use ONLY the structured metrics and summaries provided. "
        "Do not invent repository names, file paths, or technologies not listed.\n"
        "Respond with a single JSON object with keys:\n"
        '- "summary": string, 3-5 sentences overview\n'
        '- "key_differences": array of strings, 4-8 bullet-level differences\n'
        '- "recommendation": string, trade-offs and which repo is stronger for maintainability vs scalability when applicable\n'
        '- "trade_offs": string, 2-4 sentences\n'
        '- "full_text": string, markdown with sections: Overview, Technology, Architecture, Risks, Scores interpretation\n'
        f"\nDATA:\n{compact}"
    )

    try:
        resp = client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.25,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )
        raw = (resp.choices[0].message.content or "").strip()
        data = json.loads(raw)
        out = {
            "summary": str(data.get("summary") or "").strip(),
            "key_differences": data.get("key_differences") if isinstance(data.get("key_differences"), list) else [],
            "recommendation": str(data.get("recommendation") or "").strip(),
            "trade_offs": str(data.get("trade_offs") or "").strip(),
            "full_text": str(data.get("full_text") or "").strip(),
        }
        logger.info("cross_repo_llm: generated comparison narrative")
        return out
    except Exception as exc:
        logger.warning("cross_repo_llm failed: %s", exc)
        return _fallback(llm_context)


def _fallback(ctx: Dict[str, Any]) -> Dict[str, Any]:
    repos = ctx.get("repos") or []
    names = ", ".join(r.get("name", "") for r in repos if isinstance(r, dict))
    return {
        "summary": f"Compared {len(repos)} repositories ({names}). Structured metrics are in the table; enable OPENAI_API_KEY for AI narrative.",
        "key_differences": [
            "Review Technology and Structure rows for stack and graph density differences.",
            "Compare normalized maintainability and scalability scores in the scores panel.",
        ],
        "recommendation": "Prefer the repository with lower tech debt score and lower dependency density unless scalability requirements favor more services.",
        "trade_offs": "Higher service counts can improve modularity but increase operational complexity.",
        "full_text": "## Overview\n\nStructured comparison uses cached architecture, tech debt, and Neo4j graph metrics.\n",
    }
