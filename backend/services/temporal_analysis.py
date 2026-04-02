"""Assemble temporal report: map commits → modules, drift, heatmap, PR insights."""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from pathlib import Path
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


def _utc_dt(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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


def _relativize_service_paths_if_needed(
    services: List[Dict[str, Any]], repo_root: Optional[str]
) -> None:
    """If DB stored absolute paths under the clone root, make them repo-relative for git path matching."""
    if not repo_root:
        return
    try:
        base = Path(repo_root).resolve()
    except OSError:
        return
    for s in services:
        raw = (s.get("file_path") or "").strip()
        if not raw:
            continue
        try:
            p = Path(raw)
        except OSError:
            continue
        if not p.is_absolute():
            continue
        try:
            rel = p.resolve().relative_to(base)
            s["file_path"] = str(rel).replace("\\", "/")
        except ValueError:
            logger.debug(
                "temporal: service path not under clone root, leaving as-is: %s",
                raw[:120],
            )


# Suffixes that suggest ``file_path`` is a file; we also match commits under its parent folder.
_KNOWN_SOURCE_SUFFIXES = (
    ".py",
    ".pyi",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".java",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".cs",
    ".kt",
    ".swift",
    ".scala",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".cc",
    ".vue",
    ".svelte",
    ".m",
    ".mm",
    ".sql",
    ".gradle",
    ".xml",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".mdx",
)


def _normalize_repo_relative_path(path: str) -> str:
    p = (path or "").replace("\\", "/").strip()
    while p.startswith("./"):
        p = p[2:]
    p = p.lstrip("/")
    while "//" in p:
        p = p.replace("//", "/")
    return p


_NAME_SLUG_GENERIC = frozenset(
    {
        "src",
        "lib",
        "core",
        "main",
        "app",
        "test",
        "tests",
        "pkg",
        "util",
        "utils",
        "common",
        "shared",
        "internal",
        "public",
        "private",
        "java",
        "go",
        "js",
        "ts",
        "py",
        "php",
        "rb",
    }
)


def _temporal_service_name_slug(s: Dict[str, Any]) -> Optional[str]:
    """Short display name usable as a repo top-level or folder prefix (not a UUID)."""
    nm = (s.get("name") or "").strip()
    if len(nm) < 2 or len(nm) > 64:
        return None
    if re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        nm,
        re.I,
    ):
        return None
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$", nm):
        return None
    low = nm.lower()
    if low in _NAME_SLUG_GENERIC:
        return None
    return low


def _service_path_prefixes(services: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
    """
    (service_id, path_prefix) pairs for longest-prefix matching.
    Includes the stored file_path plus, for file-like paths, the parent directory so
    sibling files in the same module map to the same service.
    When ``file_path`` is empty, falls back to a unique non-generic service ``name`` slug
    (e.g. ``api``, ``backend``) so commits under ``api/...`` still map.
    """
    slug_counts: Counter[str] = Counter()
    for s in services:
        slug = _temporal_service_name_slug(s)
        if slug:
            slug_counts[slug] += 1

    pairs: List[Tuple[str, str]] = []
    seen: Set[Tuple[str, str]] = set()
    for s in services:
        sid = str(s.get("id") or "").strip()
        if not sid:
            continue
        fp = _normalize_repo_relative_path(s.get("file_path") or "")
        if fp:
            key = (sid, fp)
            if key not in seen:
                seen.add(key)
                pairs.append(key)
            low = fp.lower()
            if any(low.endswith(ext) for ext in _KNOWN_SOURCE_SUFFIXES) and "/" in fp:
                parent = fp.rsplit("/", 1)[0]
                if parent:
                    key = (sid, parent)
                    if key not in seen:
                        seen.add(key)
                        pairs.append(key)
        slug = _temporal_service_name_slug(s)
        if slug and slug_counts.get(slug, 0) == 1:
            key = (sid, slug)
            if key not in seen:
                seen.add(key)
                pairs.append(key)
    pairs.sort(key=lambda x: len(x[1]), reverse=True)
    return pairs


def map_file_to_service(rel_path: str, services: List[Dict[str, Any]]) -> Optional[str]:
    """Map a repo-relative commit path to a service id (longest path prefix wins)."""
    return map_file_to_service_with_prefixes(rel_path, _service_path_prefixes(services))


def map_file_to_service_with_prefixes(
    rel_path: str, path_prefixes: List[Tuple[str, str]]
) -> Optional[str]:
    rel = _normalize_repo_relative_path(rel_path)
    if not rel:
        return None
    rel_low = rel.lower()
    best_id: Optional[str] = None
    best_len = -1
    for sid, prefix in path_prefixes:
        if not prefix:
            continue
        pfx_low = prefix.lower()
        if rel_low == pfx_low or rel_low.startswith(pfx_low + "/"):
            if len(prefix) > best_len:
                best_len = len(prefix)
                best_id = sid
    return best_id


def _map_file_to_service_cached(
    rel_path: str,
    path_prefixes: List[Tuple[str, str]],
    cache: Dict[str, Optional[str]],
) -> Optional[str]:
    rel = _normalize_repo_relative_path(rel_path)
    if rel in cache:
        return cache[rel]
    sid = map_file_to_service_with_prefixes(rel, path_prefixes)
    cache[rel] = sid
    return sid


def _service_name_by_id(services: List[Dict[str, Any]]) -> Dict[str, str]:
    return {s["id"]: s.get("name") or s["id"] for s in services}


def _commit_modules(
    c: CommitRecord,
    path_prefixes: List[Tuple[str, str]],
    file_service_cache: Optional[Dict[str, Optional[str]]] = None,
) -> Tuple[List[str], List[str]]:
    cache = file_service_cache if file_service_cache is not None else {}
    mods: Set[str] = set()
    touched: List[str] = []
    for f in c.files_changed:
        sid = _map_file_to_service_cached(f, path_prefixes, cache)
        if sid:
            mods.add(sid)
            touched.append(f)
    return sorted(mods), touched


def _window_churn(
    commits: List[CommitRecord],
    path_prefixes: List[Tuple[str, str]],
    days: int,
    end: datetime,
    file_service_cache: Optional[Dict[str, Optional[str]]] = None,
) -> Dict[str, int]:
    start = end - timedelta(days=days)
    churn: Dict[str, int] = defaultdict(int)
    for c in commits:
        if c.committed_at < start or c.committed_at > end:
            continue
        mods, _ = _commit_modules(c, path_prefixes, file_service_cache)
        for m in mods:
            churn[m] += 1
    return dict(churn)


def _churn_from_commit_list(
    commits: List[CommitRecord],
    path_prefixes: List[Tuple[str, str]],
    file_service_cache: Optional[Dict[str, Optional[str]]] = None,
) -> Dict[str, int]:
    """Module touch counts across the given commits only (temporal sample window)."""
    churn: Dict[str, int] = defaultdict(int)
    for c in commits:
        mods, _ = _commit_modules(c, path_prefixes, file_service_cache)
        for m in mods:
            churn[m] += 1
    return dict(churn)


def _split_commit_churn_halves(
    commits: List[CommitRecord],
    path_prefixes: List[Tuple[str, str]],
    file_service_cache: Optional[Dict[str, Optional[str]]] = None,
) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Older half vs newer half (by commit date) for drift acceleration hints."""
    if not commits:
        return {}, {}
    ordered = sorted(commits, key=lambda c: c.committed_at)
    n = len(ordered)
    if n == 1:
        return {}, _churn_from_commit_list(ordered, path_prefixes, file_service_cache)
    mid = n // 2
    first = ordered[:mid]
    second = ordered[mid:]
    return (
        _churn_from_commit_list(first, path_prefixes, file_service_cache),
        _churn_from_commit_list(second, path_prefixes, file_service_cache),
    )


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
    path_prefixes: List[Tuple[str, str]],
    max_commit_events: int = 10,
    max_pr_events: int = 10,
    file_service_cache: Optional[Dict[str, Optional[str]]] = None,
) -> List[Dict[str, Any]]:
    commits = commits[:max_commit_events]
    prs = prs[:max_pr_events]
    commit_events: List[Dict[str, Any]] = []
    pr_events: List[Dict[str, Any]] = []
    names = _service_name_by_id(services)

    for c in commits:
        mods, _ = _commit_modules(c, path_prefixes, file_service_cache)
        big = len(c.files_changed) >= 18 or c.total_lines_changed >= 400
        commit_events.append(
            {
                "id": f"commit-{c.short_sha}",
                "type": "commit",
                "timestamp": c.committed_at.isoformat(),
                "author": c.author_name or c.author_email,
                "summary": c.subject,
                "impacted_modules": [names.get(m, m) for m in mods][:12],
                "impacted_service_ids": mods[:12],
                "meta": {
                    "sha": c.short_sha,
                    "files": len(c.files_changed),
                    "lines": c.total_lines_changed,
                    "major": big,
                    "body_preview": c.body_preview[:320],
                    "file_sample": c.files_changed[:6],
                },
            }
        )

    for pr in prs:
        mods: List[str] = []
        pr_events.append(
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
                    "commits": pr.commits,
                    "head_ref": pr.head_ref,
                    "base_ref": pr.base_ref,
                    "body_preview": pr.body_preview[:320],
                },
            }
        )

    events = [*commit_events, *pr_events]
    events = [e for e in events if e.get("timestamp")]
    events.sort(key=lambda x: x["timestamp"], reverse=True)
    return events[: max_commit_events + max_pr_events]


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


def _drift_statements_sample(
    churn_full: Dict[str, int],
    churn_first: Dict[str, int],
    churn_second: Dict[str, int],
    degrees: Dict[str, int],
    names: Dict[str, str],
    n_commits: int,
    n_prs: int,
    n_comments: int,
    *,
    n_services: int,
    n_services_with_paths: int,
    pr_skip_reason: Optional[str],
) -> List[str]:
    """Drift lines scoped to the sampled commits / PRs / comments only."""
    statements: List[str] = []
    denom = max(n_commits, 1)

    if n_commits > 0:
        statements.append(
            f"Drift uses the newest {n_commits} commit(s) in the sample; touches are mapped to your service inventory."
        )

    module_lines: List[str] = []
    sorted_churn = sorted(churn_full.items(), key=lambda x: -x[1])
    for rank, (sid, n) in enumerate(sorted_churn):
        if rank >= 8:
            break
        prev = churn_first.get(sid, 0)
        now = churn_second.get(sid, 0)
        deg = degrees.get(sid, 0)
        label = names.get(sid, sid)
        # Thresholds relaxed for small samples (e.g. 10 commits)
        if n >= 2 and deg >= 6:
            module_lines.append(
                f"Module «{label}» is highly connected (graph degree ~{deg}) and "
                f"appears in {n}/{denom} sampled commits — review coupling risk."
            )
        elif n >= 2:
            module_lines.append(
                f"Module «{label}» is touched in {n}/{denom} sampled commits."
            )
        elif prev > 0 and now > prev and now >= 1:
            module_lines.append(
                f"Churn rose for «{label}» in the newer half of the sample ({prev} → {now})."
            )
        elif n >= 1 and deg >= 4:
            module_lines.append(
                f"Module «{label}» (graph degree ~{deg}) has {n} touch(es) in this sample."
            )
        elif n >= 1 and rank < 3:
            module_lines.append(
                f"Module «{label}» appears in {n} sampled commit(s)."
            )

    if module_lines:
        statements.extend(module_lines)
    elif n_commits > 0 and churn_full:
        sid, n = max(churn_full.items(), key=lambda x: x[1])
        statements.append(
            f"Most activity in sample: «{names.get(sid, sid)}» ({n} file→module touch(es))."
        )
    elif n_commits > 0 and not churn_full:
        if n_services == 0:
            statements.append(
                "No services are in the inventory yet—finish repository analysis (documentation / "
                "dependency mapping) so commit files can be tied to modules."
            )
        elif n_services_with_paths == 0:
            statements.append(
                "Services exist but none have a stored file path—re-run analysis or check persistence; "
                "temporal mapping matches commit paths to each service's path prefix."
            )
        else:
            statements.append(
                "Sampled commits did not touch paths that match your service path prefixes—"
                "if the repo layout changed, re-run analysis; commits use repo-relative paths."
            )

    if n_prs:
        statements.append(f"GitHub sample: {n_prs} merged PR(s) (newest first).")
    elif n_commits > 0:
        if pr_skip_reason == "no_github_coords":
            statements.append(
                "Merged PRs are not loaded—this repository has no GitHub owner/name on record. "
                "Start analysis from the GitHub tab or a github.com URL so PR sampling can run."
            )
        elif pr_skip_reason == "no_token":
            statements.append(
                "Merged PRs are not loaded—set `GITHUB_TOKEN` on the API server. "
                "Tokens entered only on Analyze are used for cloning and are not stored for GitHub API calls."
            )
        elif pr_skip_reason == "github_api_error":
            statements.append(
                "Merged PRs could not be read from GitHub—check token access to the repository "
                "and that owner/repo names are correct."
            )
        elif pr_skip_reason == "github_sdk_missing":
            statements.append("Merged PRs are unavailable—PyGithub is not installed on the API server.")
        else:
            statements.append(
                "No merged PRs matched the current time filters, or this repository has little/no "
                "merged PR history on GitHub in the sampled window."
            )

    if n_comments:
        statements.append(f"GitHub sample: {n_comments} recent PR comment(s) for theme scanning.")

    return statements[:12]


def _pr_insights(prs: List[PRRecord]) -> Dict[str, Any]:
    large = []
    hotfixes = []
    recent = []

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
        recent.append(
            {
                "number": pr.number,
                "title": pr.title,
                "author": pr.author,
                "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
                "changed_files": pr.changed_files,
                "commits": pr.commits,
                "additions": pr.additions,
                "deletions": pr.deletions,
                "head_ref": pr.head_ref,
                "base_ref": pr.base_ref,
                "body_preview": pr.body_preview[:600],
            }
        )

    return {
        "large_prs": large[:10],
        "hotfix_patterns": hotfixes[:10],
        "repeat_files": [],  # filled from commits if needed
        "recent_prs": recent[:10],
    }


def _comment_intelligence(comment_samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    bug_kw = re.compile(r"\b(bug|regression|broken|crash|error|fix)\b", re.I)
    themes: List[str] = []
    for c in comment_samples:
        body = c.get("body_preview") or ""
        if bug_kw.search(body):
            themes.append(f"PR #{c.get('pr')}: discussion mentions defects or fixes.")
    return {"themes": themes[:10], "sampled": comment_samples[:10]}


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
            f"Graph connectivity ~{fan}; {ch} commit touch(es) in sampled window."
            if ch or fan
            else "No module touches in sampled commits."
        )
        rows.append(
            {
                "service_id": sid,
                "name": names.get(sid, sid),
                "fan_in_out": fan,
                "commits_window_touching": ch,
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
    *,
    sample_window: bool = False,
) -> List[Dict[str, str]]:
    """Build compact, UI-friendly insight cards from temporal signals."""
    names = _service_name_by_id(services)
    items: List[Dict[str, str]] = []
    min_spike = 2 if sample_window else 3

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
        if now >= min_spike and (prev == 0 or now >= max(2, int(prev * 1.8))):
            growth_candidates.append((sid, prev, now))
    growth_candidates.sort(key=lambda x: x[2], reverse=True)
    if growth_candidates:
        sid, prev, now = growth_candidates[0]
        win = "sampled commit window" if sample_window else "last 30-day window"
        items.append(
            {
                "severity": "high" if now >= 8 else "medium",
                "title": "Churn spike detected",
                "detail": f"{names.get(sid, sid)} increased from {prev} to {now} touches in the {win}.",
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
                "detail": "For the sampled commits/PRs, churn and graph signals look stable.",
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
                "change_count_window": cnt,
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
    max_commits: int = 10,
    max_prs: int = 10,
    max_comments: int = 10,
) -> Dict[str, Any]:
    max_commits = min(max(1, max_commits), 500)
    max_prs = min(max(1, max_prs), 100)
    max_comments = min(max(1, max_comments), 100)

    resolved = resolve_repository_id(db, repository_id) or repository_id
    repo_row = db.query(Repository).filter(Repository.id == resolved).first()
    if not repo_row:
        raise ValueError("Repository not found")
    if not repo_row.local_path:
        raise ValueError("Repository has no local clone path")

    now = datetime.now(timezone.utc)
    # When the client omits both since and until, do NOT apply a default 90-day git filter:
    # mature libs (e.g. click) often have no commits in the last 90 days, which yielded 0 results.
    # Instead, load the newest max_commits commits regardless of age (no --since/--until in git).
    user_set_since = since is not None
    user_set_until = until is not None
    use_git_date_filter = user_set_since or user_set_until

    since_eff: Optional[datetime] = None
    until_eff: Optional[datetime] = None
    if use_git_date_filter:
        until_eff = _utc_dt(until) if until else now
        if since is not None:
            since_eff = _utc_dt(since)
        else:
            since_eff = until_eff - timedelta(days=90)
        git_since = since_eff
        git_until = until_eff
        pr_since = since_eff
        pr_until = until_eff
    else:
        git_since = None
        git_until = None
        pr_since = None
        pr_until = None

    branch = repo_row.branch or "main"
    services = _services_for_repo(db, resolved)
    _relativize_service_paths_if_needed(services, repo_row.local_path)
    path_prefixes = _service_path_prefixes(services)
    n_services_with_paths = sum(1 for s in services if (s.get("file_path") or "").strip())
    file_service_cache: Dict[str, Optional[str]] = {}
    commits = list_commits(
        repo_row.local_path,
        branch=branch,
        since=git_since,
        until=git_until,
        max_count=max_commits,
        author_filter=author,
    )
    commits = commits[:max_commits]

    owner, gh_repo = repo_row.github_owner, repo_row.github_repo
    prs, comment_samples, pr_skip_reason = fetch_pull_requests(
        owner or "",
        gh_repo or "",
        since=pr_since,
        until=pr_until,
        max_prs=max_prs,
        max_comments=max_comments,
    )

    if module_service_id:
        sid = module_service_id.strip()
        commits = [
            c
            for c in commits
            if sid in _commit_modules(c, path_prefixes, file_service_cache)[0]
        ][:max_commits]

    churn_full = _churn_from_commit_list(commits, path_prefixes, file_service_cache)
    churn_first, churn_second = _split_commit_churn_halves(commits, path_prefixes, file_service_cache)
    degrees = _graph_degrees(resolved)
    names = _service_name_by_id(services)

    drift_statements = _drift_statements_sample(
        churn_full,
        churn_first,
        churn_second,
        degrees,
        names,
        len(commits),
        len(prs),
        len(comment_samples),
        n_services=len(services),
        n_services_with_paths=n_services_with_paths,
        pr_skip_reason=pr_skip_reason,
    )
    heatmap = build_heatmap(churn_full, services)
    timeline = build_timeline_events(
        commits,
        prs,
        services,
        path_prefixes,
        max_commit_events=max_commits,
        max_pr_events=max_prs,
        file_service_cache=file_service_cache,
    )
    pr_block = _pr_insights(prs)
    comments_block = _comment_intelligence(comment_samples)
    impact = _impact_evolution(services, churn_full, degrees)

    # Repeat file analysis (commits)
    file_hits: Counter[str] = Counter()
    for c in commits:
        for f in c.files_changed[:200]:
            file_hits[f] += 1
    repeat_files = [
        {"path": p, "commits": n} for p, n in file_hits.most_common(10) if n >= 2
    ]
    pr_block["repeat_files"] = repeat_files
    structured = _structured_insights(
        services,
        churn_full,
        churn_first,
        degrees,
        pr_block,
        sample_window=True,
    )

    drift_metrics: Dict[str, Any] = {
        "module_churn_window": churn_full,
        "module_churn_30d": churn_full,
        "module_churn_first_half": churn_first,
        "module_churn_second_half": churn_second,
        "module_churn_prev_30d": churn_first,
        "statements": drift_statements,
        "dependency_change_events": [],
        "commits_in_window": len(commits),
        "prs_in_window": len(prs),
        "comments_in_window": len(comment_samples),
        "sample_limits": {"max_commits": max_commits, "max_prs": max_prs, "max_comments": max_comments},
    }

    if use_git_date_filter and since_eff is not None and until_eff is not None:
        time_range: Dict[str, Any] = {
            "since": since_eff.isoformat(),
            "until": until_eff.isoformat(),
            "mode": "calendar",
        }
    elif commits:
        ctimes = [c.committed_at for c in commits]
        time_range = {
            "since": min(ctimes).isoformat(),
            "until": max(ctimes).isoformat(),
            "mode": "recent_commits",
            "note": (
                f"Newest {len(commits)} sampled commit(s); drift/heatmap use this sample only. "
                "No since/until filter (avoids empty history on older repos)."
            ),
        }
    else:
        time_range = {
            "since": None,
            "until": None,
            "mode": "recent_commits",
            "note": "No commits returned (check branch, shallow clone depth, or repo path).",
        }

    debug = {
        "commits_processed": len(commits),
        "prs_loaded": len(prs),
        "comments_loaded": len(comment_samples),
        "modules_mapped": len(services),
        "services_with_paths": n_services_with_paths,
        "pr_skip_reason": pr_skip_reason,
        "time_range": time_range,
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
