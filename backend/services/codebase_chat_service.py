"""
RAG-backed codebase Q&A: retrieve service/graph context, then LLM with strict grounding.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from core.config import get_settings
from core.database import SessionLocal
from models.service import Service as ServiceRow
from services.graph_service import GraphService
from services.repository_scope import resolve_repository_id

logger = logging.getLogger(__name__)
settings = get_settings()

DOC_CHAR_CAP = 12000
RETRIEVAL_CANDIDATE_K = 18
TOKEN_RE = re.compile(r"[a-zA-Z0-9_./:-]+")
STOP_WORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "for",
    "in",
    "on",
    "with",
    "what",
    "which",
    "where",
    "when",
    "does",
    "is",
    "are",
    "do",
    "if",
    "i",
    "we",
    "they",
    "it",
    "this",
    "that",
    "depend",
    "depends",
    "layer",
}


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (na * nb)


def _get_openai_client() -> Optional[OpenAI]:
    if not settings.openai_api_key:
        return None
    try:
        return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url or None)
    except Exception as exc:
        logger.warning("OpenAI client init failed: %s", exc)
        return None


def _load_services(db: Any, repository_id: str) -> List[Dict[str, Any]]:
    rows = db.query(ServiceRow).filter(ServiceRow.repository_id == repository_id).all()
    out: List[Dict[str, Any]] = []
    for r in rows:
        meta = r.meta_data or {}
        out.append(
            {
                "id": r.id,
                "name": r.name or "",
                "language": r.language or "",
                "summary": (r.summary or "").strip(),
                "description": (r.description or "").strip()[:6000],
                "path": r.file_path or "",
                "classification": meta.get("classification"),
                "entry_point_count": int(meta.get("entry_point_count") or 0),
            }
        )
    return out


def _service_document(s: Dict[str, Any]) -> str:
    parts = [
        f"Service id: {s['id']}",
        f"Name: {s['name']}",
        f"Language: {s.get('language') or 'unknown'}",
    ]
    if s.get("classification"):
        parts.append(f"Classification: {s['classification']}")
    if s.get("entry_point_count", 0) > 0:
        parts.append(f"Entry points: {s['entry_point_count']}")
    if s.get("path"):
        parts.append(f"Path: {s['path']}")
    if s.get("summary"):
        parts.append(f"Summary:\n{s['summary']}")
    if s.get("description"):
        parts.append(f"Documentation excerpt:\n{s['description'][:4000]}")
    return _truncate("\n".join(parts), DOC_CHAR_CAP)


def _truncate(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 3] + "..."


def _tokenize(text: str) -> List[str]:
    parts = [m.group(0).lower() for m in TOKEN_RE.finditer(text or "")]
    return [p for p in parts if len(p) > 1 and p not in STOP_WORDS]


def _keyword_score(query: str, service: Dict[str, Any]) -> float:
    q = query.lower().strip()
    toks = _tokenize(query)
    name = str(service.get("name") or "").lower()
    summary = str(service.get("summary") or "").lower()
    description = str(service.get("description") or "").lower()
    classification = str(service.get("classification") or "").lower()
    path = str(service.get("path") or "").lower()
    text = "\n".join((name, classification, path, summary, description))

    score = 0.0
    if q and q in text:
        score += 18.0
    for tok in toks:
        if tok == name:
            score += 14.0
        if tok in name:
            score += 9.0
        if tok in classification:
            score += 7.0
        if tok in path:
            score += 5.0
        if tok in summary:
            score += 4.0
        if tok in description:
            score += 2.0

    # Bias toward entry-point / API-ish services for common architecture questions.
    if any(tok in {"api", "endpoint", "http", "route"} for tok in toks):
        if "api" in classification or "endpoint" in classification:
            score += 8.0
        if int(service.get("entry_point_count") or 0) > 0:
            score += 5.0

    return score


def _retrieve_keyword(query: str, services: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
    ranked = sorted(
        ((float(_keyword_score(query, s)), idx, s) for idx, s in enumerate(services)),
        key=lambda x: (-x[0], x[1]),
    )
    picked = [s for score, _, s in ranked if score > 0][:top_k]
    if picked:
        return picked
    return services[:top_k]


def _dependency_context(repository_id: str, limit_lines: int = 120) -> str:
    try:
        gs = GraphService()
        data = gs.get_dependency_graph(repository_id)
        edges = data.get("edges") or []
        lines: List[str] = []
        for e in edges[:limit_lines]:
            s, t = e.get("source"), e.get("target")
            if s and t:
                lines.append(f"- {s} -> {t} ({e.get('type') or 'depends'})")
        if not lines:
            return "No dependency edges found in graph store for this repository."
        return "Dependency edges (service -> service):\n" + "\n".join(lines)
    except Exception as exc:
        logger.info("Graph context unavailable: %s", exc)
        return "Dependency graph could not be loaded (Neo4j unavailable or empty)."


def _embed_batch(client: OpenAI, texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    resp = client.embeddings.create(model=settings.openai_embedding_model, input=texts)
    # API returns in order
    return [d.embedding for d in resp.data]


def _create_chat_completion(client: OpenAI, **kwargs):
    """Use the same chat model as the rest of the backend (`OPENAI_MODEL` / `settings.openai_model`)."""
    model = (settings.openai_model or "").strip()
    if not model:
        raise RuntimeError("OPENAI_MODEL is not configured.")

    fallbacks = [m.strip() for m in str(settings.openai_model_fallbacks or "").split(",") if m.strip()]
    model_candidates: List[str] = []
    for m in [model, *fallbacks]:
        if m and m not in model_candidates:
            model_candidates.append(m)

    last_exc: Optional[Exception] = None
    for candidate in model_candidates:
        try:
            if candidate != model:
                logger.info("Chat model fallback attempt: %s (primary=%s)", candidate, model)
            return client.chat.completions.create(model=candidate, **kwargs)
        except Exception as exc:
            last_exc = exc
            logger.warning("Chat completion failed with model %s: %s", candidate, exc)
            continue

    attempted = ", ".join(model_candidates)
    raise RuntimeError(
        f"Chat model request failed. Attempted models: {attempted}. "
        "Check OPENAI_MODEL, OPENAI_MODEL_FALLBACKS, and API access."
    ) from last_exc


def _retrieve_numpy(
    client: OpenAI, query: str, services: List[Dict[str, Any]], top_k: int
) -> List[Dict[str, Any]]:
    if not services:
        return []
    query_vec = _embed_batch(client, [query])[0]
    docs = [_service_document(s) for s in services]
    batch_size = 16
    all_scores: List[Tuple[float, int]] = []
    for i in range(0, len(docs), batch_size):
        chunk = docs[i : i + batch_size]
        vecs = _embed_batch(client, chunk)
        for j, vec in enumerate(vecs):
            idx = i + j
            all_scores.append((_cosine(query_vec, vec), idx))
    all_scores.sort(key=lambda x: -x[0])
    picked = all_scores[:top_k]
    return [services[i] for _, i in picked]


def retrieve_context(
    repository_id: str, query: str, top_k: int = 8
) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Returns (context_block, retrieved_service_dicts, debug_info).
    """
    cache_hit = cache_get(f"chat:context:{hashlib.sha256(f'{repository_id}::{query.strip().lower()}'.encode()).hexdigest()}")
    if cache_hit:
        try:
            data = json.loads(cache_hit)
            return (
                str(data.get("context") or ""),
                data.get("retrieved") or [],
                data.get("debug") or [{"retrieval": "cached_context"}],
            )
        except (json.JSONDecodeError, TypeError):
            pass

    client = _get_openai_client()
    db = SessionLocal()
    try:
        resolved = resolve_repository_id(db, repository_id) or repository_id
        services = _load_services(db, resolved)
    finally:
        db.close()

    if not services:
        return (
            "No services found in the database for this repository. Run analysis first.",
            [],
            [{"note": "empty services"}],
        )

    candidates = _retrieve_keyword(query, services, min(len(services), max(top_k * 2, RETRIEVAL_CANDIDATE_K)))
    debug: List[Dict[str, Any]] = [
        {"retrieval": "keyword", "candidates": len(candidates), "services": len(services)}
    ]
    if client and candidates:
        try:
            retrieved = _retrieve_numpy(client, query, candidates, min(top_k, len(candidates)))
            debug.append({"rerank": "embedding_cosine", "hits": len(retrieved)})
        except Exception as exc:
            logger.warning("Chat embedding rerank failed, using keyword fallback: %s", exc)
            retrieved = candidates[:top_k]
            debug.append({"rerank": "keyword_fallback", "hits": len(retrieved)})
    else:
        retrieved = candidates[:top_k]

    dep_text = _dependency_context(resolved)
    ctx_parts = ["## Retrieved services (most relevant first)\n"]
    for s in retrieved:
        ctx_parts.append(_service_document(s))
        ctx_parts.append("---")
    ctx_parts.append("\n## Dependency context\n")
    ctx_parts.append(dep_text[:12000])

    logger.info(
        "Chat retrieval: repo=%s retrieved=%d context_chars=%d",
        resolved,
        len(retrieved),
        sum(len(p) for p in ctx_parts),
    )
    context_block = "\n".join(ctx_parts)
    cache_set(
        f"chat:context:{hashlib.sha256(f'{repository_id}::{query.strip().lower()}'.encode()).hexdigest()}",
        json.dumps(
            {
                "context": context_block,
                "retrieved": retrieved,
                "debug": debug,
            }
        ),
        ttl_sec=1800,
    )
    return context_block, retrieved, debug


STRUCTURED_JSON_INSTRUCTION = """Respond with a single JSON object only (no markdown fences) with keys:
- "summary": string, 1-3 sentences direct answer.
- "detailed": string, markdown allowed, fuller explanation grounded in context.
- "related_modules": array of {"id": string, "name": string, "reason": string} using ONLY service ids/names from context.
- "impact": string or null, only if the question implies change/blast radius; else null.
- "confidence": number between 0 and 1 reflecting how well the context supports the answer.
"""


def generate_answer(
    query: str,
    context: str,
    history: List[Dict[str, str]],
) -> Dict[str, Any]:
    client = _get_openai_client()
    if not client:
        raise RuntimeError("OPENAI_API_KEY is required.")

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert software architect analyzing a codebase. "
                "Answer based ONLY on the provided context. If the context is insufficient, say you don't know "
                "and suggest what analysis to run. Be concise but informative. Do not invent files, functions, or "
                "dependencies not evidenced in the context.\n\n"
                + STRUCTURED_JSON_INSTRUCTION
            ),
        }
    ]
    for h in history[-8:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"][:8000]})
    messages.append(
        {
            "role": "user",
            "content": f"Context:\n{context[:24000]}\n\nQuestion:\n{query}",
        }
    )

    logger.debug("LLM chat input chars: %d", sum(len(str(m.get("content", ""))) for m in messages))

    resp = _create_chat_completion(
        client,
        messages=messages,
        temperature=0.2,
        max_tokens=2000,
        response_format={"type": "json_object"},
    )
    raw = (resp.choices[0].message.content or "").strip()
    logger.info("LLM chat output length: %d", len(raw))
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {
            "summary": raw[:500],
            "detailed": raw,
            "related_modules": [],
            "impact": None,
            "confidence": 0.4,
        }

    summary = str(data.get("summary") or "").strip()
    detailed = str(data.get("detailed") or "").strip()
    related = data.get("related_modules") or []
    if not isinstance(related, list):
        related = []
    impact = data.get("impact")
    conf = float(data.get("confidence") or 0.6)
    conf = max(0.0, min(1.0, conf))

    # Build markdown answer for clients that expect a single field
    parts = [f"**Summary**\n\n{summary}"]
    if detailed:
        parts.append(f"\n\n**Details**\n\n{detailed}")
    if impact:
        parts.append(f"\n\n**Impact**\n\n{impact}")
    if related:
        lines = ["\n\n**Related modules**\n"]
        for r in related[:12]:
            if isinstance(r, dict):
                rid = r.get("id") or ""
                nm = r.get("name") or ""
                rs = r.get("reason") or ""
                lines.append(f"- `{nm}` (`{rid}`): {rs}")
        parts.append("\n".join(lines))
    answer_md = "".join(parts)

    return {
        "summary": summary,
        "detailed": detailed,
        "related_modules": related,
        "impact": impact if isinstance(impact, str) else None,
        "confidence": conf,
        "answer": answer_md,
    }


def stream_answer_tokens(query: str, context: str, history: List[Dict[str, str]]):
    """Generator of text chunks (for SSE)."""
    client = _get_openai_client()
    if not client:
        raise RuntimeError("OPENAI_API_KEY is required.")

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert software architect. Answer ONLY using the provided context. "
                "If unsure, say you don't know. Output clear markdown with sections: Summary, Details, Related modules, Impact (if relevant)."
            ),
        }
    ]
    for h in history[-8:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"][:8000]})
    messages.append(
        {
            "role": "user",
            "content": f"Context:\n{context[:24000]}\n\nQuestion:\n{query}",
        }
    )

    stream = _create_chat_completion(
        client,
        messages=messages,
        temperature=0.2,
        max_tokens=2000,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            yield delta


def cache_key(repo_id: str, query: str) -> str:
    h = hashlib.sha256(f"{repo_id}::{query.strip().lower()}".encode()).hexdigest()
    return f"chat:cache:{h}"


def cache_get(key: str) -> Optional[str]:
    try:
        from core.database import get_redis_client

        r = get_redis_client()
        v = r.get(key)
        if v is None:
            return None
        if isinstance(v, bytes):
            return v.decode("utf-8")
        return str(v)
    except Exception:
        return None


def cache_set(key: str, value: str, ttl_sec: int = 3600) -> None:
    try:
        from core.database import get_redis_client

        r = get_redis_client()
        r.setex(key, ttl_sec, value)
    except Exception:
        pass
