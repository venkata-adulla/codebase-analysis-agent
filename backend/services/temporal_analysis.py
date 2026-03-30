"""Assemble temporal report: map commits → modules, drift, heatmap, PR insights."""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from models.repository import Repository
from models.service import Service as ServiceRow
from services.graph_service import GraphService
from services.repository_scope import resolve_repository_id
from services.temporal_git_service import CommitRecord, list_commits
from services.temporal_github_service import PRRecord, fetch_pull_requests

logger = logging.getLogger(__name__)

HOTFIX_RE = re.compile(r"\b(hotfix|hot fix|emergency|rollback|revert|patch release)\b", re.I)
LARGE_PR_FILES = 35
LARGE_PR_LINES = 800


def _services_for_repo(db: Session, repository_id: str) -> List[Dict[str, Any]]:
    rows = db.query(ServiceRow).filter(ServiceRow.repository_id == repository_id).all()
    out = []
    for r in rows:
        fp = (r.file_path or "").replace("\\", "/").strip()
        out.append({"id": r.id, "name": r.name or "", "file_path": fp})
    out.sort(key=lambda x: len(x["file_path"]), reverse=True)
    return out


def map_file_to_service(rel_path: str, services: List[Dict[str, Any]]) -> Optional[str]:
    rel = rel_path.replace("\\", "/").strip()
    best_id = None
    best_len = -1
    for s in services:
        fp = s.get("file_path") or ""
        if not fp:
            continue
        if rel == fp or rel.startswith(fp + "/"):
            if len(fp) > best_len:
                best_len = len(fp)
                best_id = s["id"]
    return best_id


def _service_name_by_id(services: List[Dict[str, Any]]) -> Dict[str, str]:
    return {s["id"]: s.get("name") or s["id"] for s in services}


def _commit_modules(
    c: CommitRecord, services: List[Dict[str, Any]]
) -> Tuple[List[str], List[str]]:
    mods: Set[str] = set()
    for f in c.files_changed:
        sid = map_file_to_service(f, services)
        if sid:
            mods.add(sid)
    return sorted(mods), [f for f in c.files_changed if map_file_to_service(f, services)]


def _window_churn(
    commits: List[CommitRecord],
    services: List[Dict[str, Any]],
    days: int,
    end: datetime,
) -> Dict[str, int]:
    start = end - timedelta(days=days)
    churn: Dict[str, int] = defaultdict(int)
    for c in commits:
        if c.committed_at < start or c.committed_at > end:
            continue
        mods, _ = _commit_modules(c, services)
        for m in mods:
            churn[m] += 1
    return dict(churn)


def _graph_degrees(repository_id: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    try:
        gs = GraphService()
        data = gs.get_dependency_graph(repository_id)
        edges = data.get("edges") or []
        inc: Dict[str, int] = defaultdict(int)
        for e in edges:
            s, t = e.get("source"), e.get("target")
            if s and t:
                inc[s] += 1
                inc[t] += 1
        for nid, d in inc.items():
            out[str(nid)] = int(d)
    except Exception as exc:
        logger.info("temporal: graph degrees unavailable: %s", exc)
    return out


def build_timeline_events(
    commits: List[CommitRecord],
    prs: List[PRRecord],
    services: List[Dict[str, Any]],
    max_events: int = 200,
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []

    for c in commits:
        mods, _ = _commit_modules(c, services)
        big = len(c.files_changed) >= 18 or c.total_lines_changed >= 400
        events.append(
            {
                "id": f"commit-{c.short_sha}",
                "type": "commit",
                "timestamp": c.committed_at.isoformat(),
                "author": c.author_name or c.author_email,
                "summary": c.subject,
                "impacted_modules": [_service_name_by_id(services).get(m, m) for m in mods][:12],
                "impacted_service_ids": mods[:12],
                "meta": {
                    "sha": c.short_sha,
                    "files": len(c.files_changed),
                    "lines": c.total_lines_changed,
                    "major": big,
                },
            }
        )

    for pr in prs:
        mods: List[str] = []
        events.append(
            {
                "id": f"pr-{pr.number}",
                "type": "pr_merge",
                "timestamp": pr.merged_at.isoformat() if pr.merged_at else None,
                "author": pr.author,
                "summary": f"PR #{pr.number}: {pr.title}",
                "impacted_modules": mods,
                "impacted_service_ids": [],
                "meta": {
                    "pr_number": pr.number,
                    "additions": pr.additions,
                    "deletions": pr.deletions,
                    "changed_files": pr.changed_files,
                },
            }
        )

    events = [e for e in events if e.get("timestamp")]
    events.sort(key=lambda x: x["timestamp"], reverse=True)
    return events[:max_events]


def _drift_statements(
    churn_now: Dict[str, int],
    churn_prev: Dict[str, int],
    degrees: Dict[str, int],
    names: Dict[str, str],
) -> List[str]:
    statements: List[str] = []
    for sid, n in churn_now.items():
        prev = churn_prev.get(sid, 0)
        deg = degrees.get(sid, 0)
        if n >= 5 and deg >= 6:
            statements.append(
                f"Module «{names.get(sid, sid)}» is both highly connected (graph degree ~{deg}) "
                f"and active ({n} commits in the last 30 days) — review coupling and churn risk."
            )
        elif n >= 8:
            statements.append(
                f"Module «{names.get(sid, sid)}» changed frequently in the last 30 days ({n} commits touching it)."
            )
        elif prev > 0 and n > prev * 1.8:
            statements.append(
                f"Churn increased sharply for «{names.get(sid, sid)}» vs the prior window ({prev} → {n})."
            )
    return statements[:12]


def _pr_insights(prs: List[PRRecord]) -> Dict[str, Any]:
    large = []
    hotfixes = []
    file_touch_counter: Counter[str] = Counter()

    for pr in prs:
        lines_changed = pr.additions + pr.deletions
        if pr.changed_files >= LARGE_PR_FILES or lines_changed >= LARGE_PR_LINES:
            large.append(
                {
                    "number": pr.number,
                    "title": pr.title,
                    "changed_files": pr.changed_files,
                    "lines": lines_changed,
                }
            )
        title_body = f"{pr.title} {pr.body_preview}"
        if HOTFIX_RE.search(title_body):
            hotfixes.append({"number": pr.number, "title": pr.title})

    return {
        "large_prs": large[:15],
        "hotfix_patterns": hotfixes[:15],
        "repeat_files": [],  # filled from commits if needed
    }


def _comment_intelligence(comment_samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    bug_kw = re.compile(r"\b(bug|regression|broken|crash|error|fix)\b", re.I)
    themes: List[str] = []
    for c in comment_samples:
        body = c.get("body_preview") or ""
        if bug_kw.search(body):
            themes.append(f"PR #{c.get('pr')}: discussion mentions defects or fixes.")
    return {"themes": themes[:10], "sampled": comment_samples[:25]}


def _impact_evolution(
    services: List[Dict[str, Any]],
    churn: Dict[str, int],
    degrees: Dict[str, int],
) -> List[Dict[str, Any]]:
    names = _service_name_by_id(services)
    rows = []
    for s in services:
        sid = s["id"]
        d = degrees.get(sid, 0)
        ch = churn.get(sid, 0)
        fan = d
        risk = "low"
        if fan >= 8 and ch >= 4:
            risk = "high"
        elif fan >= 5 and ch >= 3:
            risk = "medium"
        note = (
            f"Graph connectivity ~{fan}; {ch} commit touches in last 30d."
            if ch or fan
            else "Limited recent activity in window."
        )
        rows.append(
            {
                "service_id": sid,
                "name": names.get(sid, sid),
                "fan_in_out": fan,
                "commits_30d_touching": ch,
                "risk_note": note,
                "risk_level": risk,
            }
        )
    rows.sort(key=lambda x: (-(x["fan_in_out"] + 2 * x["commits_30d_touching"])))
    return rows[:40]


def _structured_insights(
    services: List[Dict[str, Any]],
    churn_30: Dict[str, int],
    churn_prev: Dict[str, int],
    degrees: Dict[str, int],
    pr_block: Dict[str, Any],
) -> List[Dict[str, str]]:
    """Build compact, UI-friendly insight cards from temporal signals."""
    names = _service_name_by_id(services)
    items: List[Dict[str, str]] = []

    # 1) Structural risk: highly connected modules
    high_degree = sorted(
        ((sid, deg) for sid, deg in degrees.items() if deg >= 6),
        key=lambda x: x[1],
        reverse=True,
    )
    if high_degree:
        sid, deg = high_degree[0]
        items.append(
            {
                "severity": "medium",
                "title": "High-connectivity module",
                "detail": f"{names.get(sid, sid)} has graph degree {deg}; changes here may have broad impact.",
            }
        )

    # 2) Churn acceleration
    growth_candidates: List[Tuple[str, int, int]] = []
    for sid, now in churn_30.items():
        prev = churn_prev.get(sid, 0)
        if now >= 3 and (prev == 0 or now >= int(prev * 1.8)):
            growth_candidates.append((sid, prev, now))
    growth_candidates.sort(key=lambda x: x[2], reverse=True)
    if growth_candidates:
        sid, prev, now = growth_candidates[0]
        items.append(
            {
                "severity": "high" if now >= 8 else "medium",
                "title": "Churn spike detected",
                "detail": f"{names.get(sid, sid)} increased from {prev} to {now} touches in the last 30-day window.",
            }
        )

    # 3) PR risk signals
    large_prs = pr_block.get("large_prs") or []
    hotfixes = pr_block.get("hotfix_patterns") or []
    repeat_files = pr_block.get("repeat_files") or []
    if large_prs:
        worst = large_prs[0]
        items.append(
            {
                "severity": "medium",
                "title": "Large PR observed",
                "detail": f"PR #{worst.get('number')} changed {worst.get('changed_files')} files ({worst.get('lines')} lines).",
            }
        )
    if hotfixes:
        items.append(
            {
                "severity": "high",
                "title": "Hotfix-style PR activity",
                "detail": f"{len(hotfixes)} PR(s) matched hotfix/rollback patterns in title or body.",
            }
        )
    if repeat_files:
        top = repeat_files[0]
        items.append(
            {
                "severity": "low",
                "title": "Repeat churn hotspot",
                "detail": f"{top.get('path')} appeared in {top.get('commits')} commits in the selected window.",
            }
        )

    if not items:
        items.append(
            {
                "severity": "low",
                "title": "No strong temporal risk signals",
                "detail": "Recent churn, PR patterns, and graph connectivity look stable for the selected period.",
            }
        )

    return items[:6]


def build_heatmap(
    churn: Dict[str, int],
    services: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if not churn:
        mx = 1
    else:
        mx = max(churn.values()) or 1
    names = _service_name_by_id(services)
    modules = []
    for s in services:
        sid = s["id"]
        cnt = churn.get(sid, 0)
        intensity = min(1.0, cnt / max(mx, 1))
        modules.append(
            {
                "service_id": sid,
                "name": names.get(sid, sid),
                "intensity": round(intensity, 4),
                "change_count_30d": cnt,
                "stable": cnt == 0,
            }
        )
    modules.sort(key=lambda x: -x["change_count_30d"])
    return {"modules": modules, "max_churn": mx}


def run_temporal_analysis(
    db: Session,
    repository_id: str,
    *,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    author: Optional[str] = None,
    module_service_id: Optional[str] = None,
    max_commits: int = 500,
) -> Dict[str, Any]:
    resolved = resolve_repository_id(db, repository_id) or repository_id
    repo_row = db.query(Repository).filter(Repository.id == resolved).first()
    if not repo_row:
        raise ValueError("Repository not found")
    if not repo_row.local_path:
        raise ValueError("Repository has no local clone path")

    until = until or datetime.now(timezone.utc)
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    since = since or (until - timedelta(days=90))
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)

    branch = repo_row.branch or "main"
    services = _services_for_repo(db, resolved)
    commits = list_commits(
        repo_row.local_path,
        branch=branch,
        since=since,
        until=until,
        max_count=max_commits,
        author_filter=author,
    )

    owner, gh_repo = repo_row.github_owner, repo_row.github_repo
    prs, comment_samples = fetch_pull_requests(
        owner or "",
        gh_repo or "",
        since=since,
        until=until,
        max_prs=60,
    )

    if module_service_id:
        sid = module_service_id.strip()
        commits = [
            c
            for c in commits
            if sid in _commit_modules(c, services)[0]
        ]

    now = until
    churn_30 = _window_churn(commits, services, 30, now)
    churn_prev = _window_churn(commits, services, 30, now - timedelta(days=30))
    degrees = _graph_degrees(resolved)
    names = _service_name_by_id(services)

    drift_statements = _drift_statements(churn_30, churn_prev, degrees, names)
    heatmap = build_heatmap(churn_30, services)
    timeline = build_timeline_events(commits, prs, services)
    pr_block = _pr_insights(prs)
    comments_block = _comment_intelligence(comment_samples)
    impact = _impact_evolution(services, churn_30, degrees)

    # Repeat file analysis (commits)
    file_hits: Counter[str] = Counter()
    for c in commits:
        for f in c.files_changed[:200]:
            file_hits[f] += 1
    repeat_files = [
        {"path": p, "commits": n} for p, n in file_hits.most_common(15) if n >= 3
    ]
    pr_block["repeat_files"] = repeat_files
    structured = _structured_insights(services, churn_30, churn_prev, degrees, pr_block)

    drift_metrics: Dict[str, Any] = {
        "module_churn_30d": churn_30,
        "module_churn_prev_30d": churn_prev,
        "statements": drift_statements,
        "dependency_change_events": [],
        "commits_in_window": len(commits),
    }

    debug = {
        "commits_processed": len(commits),
        "prs_loaded": len(prs),
        "modules_mapped": len(services),
        "time_range": {"since": since.isoformat(), "until": until.isoformat()},
    }
    logger.info(
        "temporal analysis: commits=%d prs=%d services=%d",
        len(commits),
        len(prs),
        len(services),
    )

    return {
        "repository_id": resolved,
        "timeline": timeline,
        "drift_metrics": drift_metrics,
        "heatmap": heatmap,
        "pr_insights": pr_block,
        "comment_insights": comments_block,
        "impact_evolution": impact,
        "insights": structured,
        "debug": debug,
    }
