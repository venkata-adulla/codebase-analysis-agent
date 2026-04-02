"""GitHub PR and comment sampling for temporal analysis (optional PyGithub)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class PRRecord:
    number: int
    title: str
    body_preview: str
    merged_at: Optional[datetime]
    author: str
    additions: int
    deletions: int
    changed_files: int
    commits: int
    head_ref: str
    base_ref: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "number": self.number,
            "title": self.title,
            "body_preview": self.body_preview[:600],
            "merged_at": self.merged_at.isoformat() if self.merged_at else None,
            "author": self.author,
            "additions": self.additions,
            "deletions": self.deletions,
            "changed_files": self.changed_files,
            "commits": self.commits,
            "head_ref": self.head_ref,
            "base_ref": self.base_ref,
        }


def fetch_pull_requests(
    owner: str,
    repo_name: str,
    *,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    max_prs: int = 10,
    max_comments: int = 10,
    github_token: Optional[str] = None,
) -> tuple[List[PRRecord], List[Dict[str, Any]], Optional[str]]:
    """
    Returns (merged_prs, comment_insights_sample, skip_reason).

    skip_reason explains why PRs were not loaded (for UI copy); None if GitHub was queried
    (including when the merged list is simply empty for this window).
    """
    if not owner or not repo_name:
        logger.info("temporal_github: skipping PRs (missing owner or repo name)")
        return [], [], "no_github_coords"

    token = (
        (github_token or os.environ.get("GITHUB_TOKEN") or settings.github_token or "")
        .strip()
    )
    if not token:
        logger.info("temporal_github: skipping PRs (no token on server)")
        return [], [], "no_token"

    try:
        from github import Github
    except ImportError:
        return [], [], "github_sdk_missing"

    g = Github(token, per_page=30)
    try:
        repo = g.get_repo(f"{owner}/{repo_name}")
    except Exception as exc:
        logger.warning("temporal_github: could not open repo %s/%s: %s", owner, repo_name, exc)
        return [], [], "github_api_error"

    prs: List[PRRecord] = []
    comment_samples: List[Dict[str, Any]] = []

    try:
        pulls = repo.get_pulls(state="closed", sort="updated", direction="desc")
    except Exception as exc:
        logger.warning("temporal_github: list pulls failed: %s", exc)
        return [], [], "github_api_error"

    count = 0
    for pr in pulls:
        if count >= max_prs * 3:
            break
        if not pr.merged:
            continue
        merged = pr.merged_at
        if merged:
            merged = merged.replace(tzinfo=timezone.utc) if merged.tzinfo is None else merged.astimezone(timezone.utc)
            if since and merged < since:
                continue
            if until and merged > until:
                continue
        else:
            continue

        try:
            additions = pr.additions or 0
            deletions = pr.deletions or 0
            files = pr.changed_files or 0
        except Exception:
            additions = deletions = files = 0

        raw = getattr(pr, "_rawData", None) or {}
        try:
            n_commits = int(raw.get("commits", 0))
        except Exception:
            n_commits = 0

        body = (pr.body or "")[:2000]
        prs.append(
            PRRecord(
                number=pr.number,
                title=pr.title or "",
                body_preview=body,
                merged_at=merged,
                author=(pr.user.login if pr.user else "") or "",
                additions=additions,
                deletions=deletions,
                changed_files=files,
                commits=n_commits,
                head_ref=getattr(pr.head, "ref", "") or "",
                base_ref=getattr(pr.base, "ref", "") or "",
            )
        )
        count += 1
        if len(prs) >= max_prs:
            break

    # Sample comments up to max_comments (newest PRs first; minimal API calls)
    for pr_rec in prs:
        if len(comment_samples) >= max_comments:
            break
        try:
            pr = repo.get_pull(pr_rec.number)
            for c in list(pr.get_issue_comments()):
                if len(comment_samples) >= max_comments:
                    break
                comment_samples.append(
                    {
                        "pr": pr_rec.number,
                        "pr_title": pr_rec.title,
                        "kind": "issue_comment",
                        "author": c.user.login if c.user else "",
                        "body_preview": (c.body or "")[:600],
                        "created_at": c.created_at.isoformat() if c.created_at else None,
                    }
                )
            for c in list(pr.get_review_comments()):
                if len(comment_samples) >= max_comments:
                    break
                comment_samples.append(
                    {
                        "pr": pr_rec.number,
                        "pr_title": pr_rec.title,
                        "kind": "review_comment",
                        "author": c.user.login if c.user else "",
                        "body_preview": (c.body or "")[:600],
                        "created_at": c.created_at.isoformat() if c.created_at else None,
                    }
                )
        except Exception:
            pass
    comment_samples.sort(
        key=lambda x: str(x.get("created_at") or ""),
        reverse=True,
    )
    comment_samples = comment_samples[:max_comments]
    logger.info("temporal_github: fetched %d merged PRs", len(prs))
    return prs, comment_samples, None
