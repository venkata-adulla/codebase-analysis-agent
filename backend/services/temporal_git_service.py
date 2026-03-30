"""Git history ingestion for temporal / drift analysis (GitPython)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CommitRecord:
    sha: str
    short_sha: str
    author_name: str
    author_email: str
    committed_at: datetime  # UTC
    subject: str
    body_preview: str
    files_changed: List[str]
    insertions: int
    deletions: int
    total_lines_changed: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sha": self.sha,
            "short_sha": self.short_sha,
            "author_name": self.author_name,
            "author_email": self.author_email,
            "committed_at": self.committed_at.isoformat(),
            "subject": self.subject,
            "body_preview": self.body_preview[:500],
            "files_changed": self.files_changed,
            "insertions": self.insertions,
            "deletions": self.deletions,
            "total_lines_changed": self.total_lines_changed,
        }


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# Note: Per-commit diffs are bounded by max_count; for very large repos consider lowering max_count.


def list_commits(
    repo_path: str,
    *,
    branch: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    max_count: int = 600,
    author_filter: Optional[str] = None,
) -> List[CommitRecord]:
    """Walk commit history newest-first. Caps work for large repos."""
    try:
        from git import Repo
    except ImportError as exc:
        raise RuntimeError("GitPython is required for temporal analysis") from exc

    root = Path(repo_path)
    if not root.is_dir():
        raise ValueError(f"Not a directory: {repo_path}")

    repo = Repo(str(root))
    rev = branch or "HEAD"
    try:
        repo.git.rev_parse("--verify", rev)
    except Exception:
        rev = "HEAD"

    kwargs: Dict[str, Any] = {"max_count": max_count}
    if since:
        kwargs["since"] = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
    if until:
        kwargs["until"] = until if until.tzinfo else until.replace(tzinfo=timezone.utc)

    commits_iter = repo.iter_commits(rev, **kwargs)
    out: List[CommitRecord] = []

    author_re = None
    if author_filter and author_filter.strip():
        author_re = re.compile(re.escape(author_filter.strip()), re.I)

    for commit in commits_iter:
        try:
            committed = _utc(datetime.fromtimestamp(commit.committed_date, tz=timezone.utc))
        except Exception:
            continue

        author = commit.author or commit.committer
        aname = (author.name if author else "") or ""
        aemail = (author.email if author else "") or ""
        if author_re and not (author_re.search(aname) or author_re.search(aemail)):
            continue

        subj, _, body = (commit.message or "").partition("\n")
        subj = (subj or "").strip()
        body = body.strip()

        files: List[str] = []
        ins = dels = 0
        try:
            if commit.parents:
                diff_index = commit.parents[0].diff(commit, create_patch=False)
                for d in diff_index:
                    p = d.b_path or d.a_path
                    if p:
                        files.append(str(p).replace("\\", "/"))
                st = commit.stats.total
                ins = int(st.get("insertions", 0) or 0)
                dels = int(st.get("deletions", 0) or 0)
            else:
                if commit.tree:
                    for blob in commit.tree.traverse():
                        if blob.type == "blob":
                            files.append(str(blob.path).replace("\\", "/"))
        except Exception as exc:
            logger.debug("commit diff stats: %s", exc)

        total_lc = ins + dels
        if not files and commit.stats.files:
            files = list(commit.stats.files.keys())

        out.append(
            CommitRecord(
                sha=commit.hexsha,
                short_sha=commit.hexsha[:7],
                author_name=aname,
                author_email=aemail,
                committed_at=committed,
                subject=subj or "(no subject)",
                body_preview=body[:800],
                files_changed=sorted(set(files)),
                insertions=ins,
                deletions=dels,
                total_lines_changed=total_lc,
            )
        )

    logger.info("temporal_git: collected %d commits (rev=%s)", len(out), rev)
    return out
