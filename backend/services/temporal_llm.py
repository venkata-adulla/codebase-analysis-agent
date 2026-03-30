"""LLM layer for temporal / drift narratives."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

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
        logger.warning("temporal_llm: OpenAI init failed: %s", exc)
        return None


def enrich_temporal_insights(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Adds: insights[], ai_summary { drift_summary, risky_modules, anomalies }.
    """
    client = _client()
    drift = payload.get("drift_metrics") or {}
    heat = payload.get("heatmap") or {}
    pr_i = payload.get("pr_insights") or {}
    dbg = payload.get("debug") or {}

    fallback = _fallback_insights(payload)

    compact = {
        "drift_statements": (drift.get("statements") or [])[:10],
        "heatmap_top": (heat.get("modules") or [])[:12],
        "large_prs": (pr_i.get("large_prs") or [])[:8],
        "hotfixes": (pr_i.get("hotfix_patterns") or [])[:8],
        "repeat_files": (pr_i.get("repeat_files") or [])[:8],
        "commits_in_window": drift.get("commits_in_window") or dbg.get("commits_processed"),
    }

    if not client:
        return fallback

    prompt = (
        "You are analyzing code evolution over time. Identify risks, trends, and anomalies "
        "using ONLY the structured facts below. Do not invent commit hashes or authors.\n"
        "Respond with a single JSON object with keys:\n"
        '- "insights": array of { "severity": "low"|"medium"|"high", "title": string, "detail": string }, max 8\n'
        '- "drift_summary": string, 2-4 sentences\n'
        '- "risky_modules": string, list module names or themes at risk\n'
        '- "anomalies": string, unusual patterns (spikes, large PRs, hotfixes)\n'
        f"\nFACTS:\n{json.dumps(compact, indent=2)}"
    )

    try:
        resp = client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1200,
            response_format={"type": "json_object"},
        )
        raw = (resp.choices[0].message.content or "").strip()
        data = json.loads(raw)
        insights = data.get("insights") or []
        if not isinstance(insights, list):
            insights = []
        norm: List[Dict[str, Any]] = []
        for i in insights[:10]:
            if isinstance(i, dict) and i.get("title"):
                norm.append(
                    {
                        "severity": str(i.get("severity") or "medium").lower(),
                        "title": str(i.get("title", ""))[:200],
                        "detail": str(i.get("detail", ""))[:800],
                    }
                )
        out = {
            "insights": norm,
            "ai_summary": {
                "drift_summary": str(data.get("drift_summary") or "").strip(),
                "risky_modules": str(data.get("risky_modules") or "").strip(),
                "anomalies": str(data.get("anomalies") or "").strip(),
            },
        }
        logger.info("temporal_llm: generated %d insights", len(norm))
        return out
    except Exception as exc:
        logger.warning("temporal_llm failed: %s", exc)
        return fallback


def _fallback_insights(payload: Dict[str, Any]) -> Dict[str, Any]:
    drift = payload.get("drift_metrics") or {}
    statements = drift.get("statements") or []
    insights: List[Dict[str, Any]] = []
    for i, s in enumerate(statements[:6]):
        insights.append(
            {
                "severity": "medium",
                "title": f"Drift signal {i + 1}",
                "detail": s,
            }
        )
    pr_i = payload.get("pr_insights") or {}
    for lp in (pr_i.get("large_prs") or [])[:2]:
        insights.append(
            {
                "severity": "high",
                "title": f"Large PR #{lp.get('number')}",
                "detail": lp.get("title", "")[:300],
            }
        )
    return {
        "insights": insights[:10],
        "ai_summary": {
            "drift_summary": " ".join(statements[:3]) if statements else "Not enough history for a drift narrative.",
            "risky_modules": "See heatmap and impact table for modules with high churn and connectivity.",
            "anomalies": f"Hotfix-style PRs: {len(pr_i.get('hotfix_patterns') or [])}. Large PRs: {len(pr_i.get('large_prs') or [])}.",
        },
    }
