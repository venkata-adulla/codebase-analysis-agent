"""
Cross-repository comparison using cached architecture reports, tech debt, and graph metrics.
Does not re-run static analysis — reads Redis + DB + Neo4j only.
"""

from __future__ import annotations

import json
import logging
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from models.repository import Repository
from models.service import Service as ServiceRow
from models.tech_debt import TechDebtReport
from services.graph_service import GraphService
from services.repository_scope import resolve_repository_id

logger = logging.getLogger(__name__)

ARCHITECTURE_CACHE_PREFIX = "architecture:report:"


def _architecture_cache_get(repository_id: str) -> Optional[Dict[str, Any]]:
    try:
        from core.database import get_redis_client

        r = get_redis_client()
        key = f"{ARCHITECTURE_CACHE_PREFIX}{repository_id}"
        v = r.get(key)
        if v is None:
            return None
        if isinstance(v, bytes):
            v = v.decode("utf-8")
        return json.loads(v)
    except Exception as exc:
        logger.debug("architecture cache read: %s", exc)
        return None


def _service_count(db: Session, repository_id: str) -> int:
    return db.query(ServiceRow).filter(ServiceRow.repository_id == repository_id).count()


def _latest_tech_debt(db: Session, repository_id: str) -> Optional[TechDebtReport]:
    return (
        db.query(TechDebtReport)
        .filter(TechDebtReport.repository_id == repository_id)
        .order_by(TechDebtReport.created_at.desc())
        .first()
    )


def _graph_bundle(repository_id: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "node_count": 0,
        "edge_count": 0,
        "density": 0.0,
        "cycles_approx": None,
        "architecture_summary": {},
    }
    try:
        gs = GraphService()
        data = gs.get_dependency_graph(repository_id)
        nodes = data.get("nodes") or []
        edges = data.get("edges") or []
        n, e = len(nodes), len(edges)
        out["node_count"] = n
        out["edge_count"] = e
        out["density"] = round(e / max(n, 1), 4)
        arch = data.get("architecture_summary") or {}
        out["architecture_summary"] = arch if isinstance(arch, dict) else {}
        if isinstance(arch, dict) and arch.get("cycle_count") is not None:
            out["cycles_approx"] = arch.get("cycle_count")
    except Exception as exc:
        logger.info("cross_repo: graph unavailable for %s: %s", repository_id[:12], exc)
    return out


def _stack_summary(arch: Optional[Dict[str, Any]]) -> Dict[str, str]:
    if not arch:
        return {"frontend": "—", "backend": "—", "database": "—", "other": "—"}
    by = (arch.get("technology_stack") or {}).get("by_category") or {}
    def join_cat(cat: str) -> str:
        rows = by.get(cat) or []
        names = [r.get("name", "") for r in rows if isinstance(r, dict)][:6]
        return ", ".join(names) if names else "—"
    return {
        "frontend": join_cat("frontend"),
        "backend": join_cat("backend"),
        "database": join_cat("database"),
        "other": join_cat("other"),
    }


def _style_summary(arch: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not arch:
        return {"label": "—", "class_ratio": None, "modularity": "—", "large_files": 0}
    cs = arch.get("coding_style") or {}
    lf = cs.get("large_files") or []
    return {
        "label": cs.get("label") or "—",
        "class_ratio": cs.get("class_ratio"),
        "modularity": cs.get("modularity_hint") or "—",
        "large_files": len(lf) if isinstance(lf, list) else 0,
    }


def _risk_summary(arch: Optional[Dict[str, Any]], td: Optional[TechDebtReport]) -> Dict[str, Any]:
    risks_arch = (arch.get("risks_and_practices") or {}) if arch else {}
    rlist = risks_arch.get("risks") or []
    high = sum(1 for x in rlist if isinstance(x, dict) and str(x.get("severity")).lower() == "high")
    return {
        "risk_items": len(rlist),
        "high_severity": high,
        "total_debt_score": float(td.total_debt_score) if td and td.total_debt_score is not None else None,
        "debt_items": int(td.total_items) if td and td.total_items is not None else None,
    }


def _raw_scores(
    arch: Optional[Dict[str, Any]],
    td: Optional[TechDebtReport],
    graph: Dict[str, Any],
    service_count: int,
) -> Dict[str, float]:
    """Higher maintainability/scalability = better. Higher complexity = worse (more complex)."""
    # Maintainability: lower debt is better; category scores are debt-like (higher worse)
    if td:
        debt = float(td.total_debt_score or 0)
        cq = float(td.code_quality_score or 0)
        ar = float(td.architecture_score or 0)
        dep = float(td.dependency_score or 0)
        doc = float(td.documentation_score or 0)
        tst = float(td.test_coverage_score or 0)
        avg_cat = (cq + ar + dep + doc + tst) / 5.0
        maintainability = max(0.0, min(100.0, 100.0 - debt * 0.35 - avg_cat * 0.35))
    else:
        maintainability = 55.0 if arch else 40.0

    nodes = max(1, graph.get("node_count") or 0)
    edges = graph.get("edge_count") or 0
    density = float(graph.get("density") or 0)
    # Scalability: more discrete services helps; extreme coupling hurts
    scalability = max(
        0.0,
        min(
            100.0,
            35.0 + min(40.0, service_count * 1.2) + min(25.0, nodes * 0.8) - min(40.0, density * 15.0),
        ),
    )

    cycles = graph.get("cycles_approx")
    cpen = float(cycles) * 3.0 if isinstance(cycles, (int, float)) else 0.0
    lf = 0
    if arch:
        lf = len((arch.get("coding_style") or {}).get("large_files") or [])
    complexity = max(
        0.0,
        min(100.0, density * 22.0 + cpen + lf * 2.5 + (edges / max(nodes, 1)) * 8.0),
    )

    return {
        "maintainability": round(maintainability, 2),
        "scalability": round(scalability, 2),
        "complexity": round(complexity, 2),
    }


def _normalize_across_repos(
    scores_by_repo: Dict[str, Dict[str, float]]
) -> Dict[str, Dict[str, float]]:
    """Attach raw + min–max normalized 0–100 per dimension (complexity inverted: lower raw → higher score)."""
    ids = list(scores_by_repo.keys())
    out: Dict[str, Dict[str, float]] = {rid: {} for rid in ids}
    for dim in ("maintainability", "scalability"):
        vals = [scores_by_repo[rid][dim] for rid in ids]
        lo, hi = min(vals), max(vals)
        span = (hi - lo) or 1.0
        for rid in ids:
            raw = scores_by_repo[rid][dim]
            out[rid][dim] = raw
            out[rid][f"{dim}_normalized"] = round(max(0.0, min(100.0, (raw - lo) / span * 100.0)), 2)
    vals_c = [scores_by_repo[rid]["complexity"] for rid in ids]
    lo_c, hi_c = min(vals_c), max(vals_c)
    span_c = (hi_c - lo_c) or 1.0
    for rid in ids:
        c = scores_by_repo[rid]["complexity"]
        out[rid]["complexity_risk"] = c
        inv = 100.0 - (c - lo_c) / span_c * 100.0
        out[rid]["complexity_normalized"] = round(max(0.0, min(100.0, inv)), 2)
    return out


def build_comparison_table(
    profiles: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Rows for UI table: category -> per-repo display strings."""
    repo_ids = list(profiles.keys())
    rows: List[Dict[str, Any]] = []

    def cell(rid: str, key: str, sub: Optional[str] = None) -> str:
        p = profiles[rid]
        if sub:
            block = p.get(key) or {}
            return str(block.get(sub) or "—")
        return str(p.get(key) or "—")

    rows.append(
        {
            "category": "Architecture",
            "subcategory": "Summary (cached)",
            "values": {rid: cell(rid, "arch_summary") for rid in repo_ids},
        }
    )
    rows.append(
        {
            "category": "Technology",
            "subcategory": "Frontend",
            "values": {rid: cell(rid, "stack", "frontend") for rid in repo_ids},
        }
    )
    rows.append(
        {
            "category": "Technology",
            "subcategory": "Backend",
            "values": {rid: cell(rid, "stack", "backend") for rid in repo_ids},
        }
    )
    rows.append(
        {
            "category": "Technology",
            "subcategory": "Database / data",
            "values": {rid: cell(rid, "stack", "database") for rid in repo_ids},
        }
    )
    rows.append(
        {
            "category": "Technology",
            "subcategory": "Other / infra",
            "values": {rid: cell(rid, "stack", "other") for rid in repo_ids},
        }
    )
    rows.append(
        {
            "category": "Structure",
            "subcategory": "Services (DB count)",
            "values": {rid: str(profiles[rid].get("service_count", "—")) for rid in repo_ids},
        }
    )
    rows.append(
        {
            "category": "Structure",
            "subcategory": "Graph nodes / edges",
            "values": {
                rid: f"{profiles[rid].get('graph_nodes', '—')} / {profiles[rid].get('graph_edges', '—')}"
                for rid in repo_ids
            },
        }
    )
    rows.append(
        {
            "category": "Structure",
            "subcategory": "Dependency density (edges/node)",
            "values": {rid: str(profiles[rid].get("graph_density", "—")) for rid in repo_ids},
        }
    )
    rows.append(
        {
            "category": "Coding style",
            "subcategory": "Style label",
            "values": {rid: cell(rid, "style", "label") for rid in repo_ids},
        }
    )
    rows.append(
        {
            "category": "Coding style",
            "subcategory": "Modularity hint",
            "values": {rid: cell(rid, "style", "modularity") for rid in repo_ids},
        }
    )
    rows.append(
        {
            "category": "Risk & quality",
            "subcategory": "Tech debt score (0–100)",
            "values": {
                rid: str(profiles[rid].get("debt_score", "—")) if profiles[rid].get("debt_score") is not None else "—"
                for rid in repo_ids
            },
        }
    )
    rows.append(
        {
            "category": "Risk & quality",
            "subcategory": "Automated risk items (arch)",
            "values": {rid: str((profiles[rid].get("risk") or {}).get("risk_items", "—")) for rid in repo_ids},
        }
    )
    rows.append(
        {
            "category": "Risk & quality",
            "subcategory": "Graph cycles (approx)",
            "values": {rid: str(profiles[rid].get("cycles", "—")) for rid in repo_ids},
        }
    )
    return rows


def build_cross_repo_comparison(db: Session, repository_ids: List[str]) -> Dict[str, Any]:
    """Assemble structured comparison for 2+ repositories."""
    uniq: List[str] = []
    seen = set()
    for raw in repository_ids:
        rid = (raw or "").strip()
        if not rid or rid in seen:
            continue
        seen.add(rid)
        uniq.append(rid)

    if len(uniq) < 2:
        raise ValueError("At least two distinct repository IDs are required")

    resolved_map: "OrderedDict[str, str]" = OrderedDict()
    for token in uniq:
        resolved = resolve_repository_id(db, token) or token
        if resolved not in resolved_map:
            resolved_map[resolved] = token

    if len(resolved_map) < 2:
        raise ValueError("At least two different repositories are required (duplicate IDs resolve to the same repo)")

    profiles: Dict[str, Dict[str, Any]] = {}
    scores_raw: Dict[str, Dict[str, float]] = {}

    for resolved, token in resolved_map.items():
        row = db.query(Repository).filter(Repository.id == resolved).first()
        if not row:
            raise ValueError(f"Repository not found: {token}")

        arch = _architecture_cache_get(resolved)
        td = _latest_tech_debt(db, resolved)
        graph = _graph_bundle(resolved)
        scount = _service_count(db, resolved)
        stack = _stack_summary(arch)
        style = _style_summary(arch)
        risk = _risk_summary(arch, td)

        narrative = (arch or {}).get("narrative") or {}
        arch_summary = (
            str(narrative.get("architecture_summary") or "").strip()
            or ("(Run Architecture analysis to populate cache.)" if not arch else "—")
        )

        raw_scores = _raw_scores(arch, td, graph, scount)
        scores_raw[resolved] = raw_scores

        profiles[resolved] = {
            "id": resolved,
            "name": row.name or resolved[:8],
            "query_token": token,
            "has_architecture_cache": arch is not None,
            "arch_summary": arch_summary[:1200],
            "stack": stack,
            "style": style,
            "risk": risk,
            "service_count": scount,
            "graph_nodes": graph["node_count"],
            "graph_edges": graph["edge_count"],
            "graph_density": graph["density"],
            "cycles": graph.get("cycles_approx"),
            "debt_score": float(td.total_debt_score) if td and td.total_debt_score is not None else None,
        }

    normalized = _normalize_across_repos(scores_raw)

    table = build_comparison_table(profiles)

    comparison_payload = {
        "repositories": [profiles[rid] for rid in profiles],
        "table": table,
        "scores": {
            rid: {
                "maintainability": normalized[rid].get("maintainability"),
                "scalability": normalized[rid].get("scalability"),
                "complexity_risk": normalized[rid].get("complexity_risk"),
                "maintainability_normalized": normalized[rid].get("maintainability_normalized"),
                "scalability_normalized": normalized[rid].get("scalability_normalized"),
                "complexity_normalized": normalized[rid].get("complexity_normalized"),
            }
            for rid in profiles
        },
        "structured_metrics": {
            rid: {
                "raw_scores": scores_raw[rid],
                "stack": profiles[rid]["stack"],
                "style_label": profiles[rid]["style"]["label"],
                "debt": profiles[rid]["debt_score"],
                "nodes": profiles[rid]["graph_nodes"],
                "edges": profiles[rid]["graph_edges"],
                "density": profiles[rid]["graph_density"],
            }
            for rid in profiles
        },
    }

    logger.info(
        "cross_repo_comparison: compared %d repos metrics=%s",
        len(profiles),
        list(profiles.keys()),
    )

    return {
        "comparison": comparison_payload,
        "scores": comparison_payload["scores"],
        "llm_context": {
            "repos": [
                {
                    "id": rid,
                    "name": profiles[rid]["name"],
                    "stack": profiles[rid]["stack"],
                    "style": profiles[rid]["style"]["label"],
                    "modularity": profiles[rid]["style"]["modularity"],
                    "debt_score": profiles[rid]["debt_score"],
                    "graph_density": profiles[rid]["graph_density"],
                    "services": profiles[rid]["service_count"],
                    "risk_items": profiles[rid]["risk"]["risk_items"],
                    "summary": profiles[rid]["arch_summary"][:800],
                }
                for rid in profiles
            ],
            "normalized_scores": comparison_payload["scores"],
        },
    }
