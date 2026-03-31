import os
import shutil
import logging
import uuid
from pathlib import Path
from typing import Optional, Dict, Any
from github import Github
from git import Repo, InvalidGitRepositoryError, GitCommandError
from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class RepositoryManager:
    """Manages repository access from multiple sources."""
    
    def __init__(self):
        self.repositories_dir = Path(settings.repositories_dir)
        self.repositories_dir.mkdir(parents=True, exist_ok=True)
        self.github_client: Optional[Github] = None
        
        if settings.github_token:
            try:
                self.github_client = Github(settings.github_token)
                logger.info("GitHub client initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize GitHub client: {e}")
    
    def clone_from_github(
        self,
        owner: str,
        repo: str,
        branch: Optional[str] = None
    ) -> str:
        """Clone a repository from GitHub."""
        clone_url = f"https://github.com/{owner}/{repo}.git"

        if self.github_client:
            try:
                github_repo = self.github_client.get_repo(f"{owner}/{repo}")
                clone_url = github_repo.clone_url
            except Exception as e:
                logger.warning(f"Github token available but unable to resolve repo via API: {e}. Falling back to https URL")

        try:
            repo_id = str(uuid.uuid4())
            local_path = self.repositories_dir / repo_id
            self._clone_with_branch_fallback(clone_url, local_path, branch)
            logger.info(f"Cloned {owner}/{repo} to {local_path}")
            return str(local_path)
        except GitCommandError as e:
            raise ValueError(self._friendly_git_error(e, branch)) from e
        except Exception as e:
            logger.error(f"Failed to clone from GitHub: {e}")
            raise
    
    def clone_from_url(
        self,
        url: str,
        branch: Optional[str] = None
    ) -> str:
        """Clone a repository from a Git URL."""
        try:
            repo_id = str(uuid.uuid4())
            local_path = self.repositories_dir / repo_id
            self._clone_with_branch_fallback(url, local_path, branch)
            logger.info(f"Cloned {url} to {local_path}")
            return str(local_path)
        except GitCommandError as e:
            raise ValueError(self._friendly_git_error(e, branch)) from e
        except Exception as e:
            logger.error(f"Failed to clone from URL: {e}")
            raise

    def _clone_with_branch_fallback(
        self,
        clone_url: str,
        local_path: Path,
        branch: Optional[str] = None,
    ) -> None:
        """Clone repo, retrying default branch when an explicit branch is missing."""
        try:
            if branch:
                Repo.clone_from(clone_url, str(local_path), branch=branch)
            else:
                Repo.clone_from(clone_url, str(local_path))
            return
        except GitCommandError as exc:
            err = str(exc).lower()
            missing_branch = branch and "remote branch" in err and "not found" in err
            if not missing_branch:
                raise
            logger.warning(
                "Branch '%s' not found for %s; retrying clone with repository default branch.",
                branch,
                clone_url,
            )
            if local_path.exists():
                shutil.rmtree(str(local_path), ignore_errors=True)
            Repo.clone_from(clone_url, str(local_path))

    def _friendly_git_error(self, exc: GitCommandError, branch: Optional[str]) -> str:
        raw = str(exc)
        low = raw.lower()
        if branch and "remote branch" in low and "not found" in low:
            return (
                f"Branch '{branch}' does not exist on the remote repository. "
                "Try leaving branch empty or use the repository default branch."
            )
        if "authentication failed" in low or "could not read username" in low:
            return "Authentication failed while cloning repository. Check repository access/token."
        if "connect tunnel failed" in low or "failed to connect" in low:
            return "Unable to reach Git host from API server. Check outbound network/proxy settings."
        return f"Git clone failed: {raw}"
    
    def use_local_path(
        self,
        path: str
    ) -> str:
        """Use an existing local repository path."""
        local_path = Path(path)
        
        if not local_path.exists():
            raise ValueError(f"Path does not exist: {path}")
        
        # Verify it's a git repository
        try:
            Repo(str(local_path))
        except InvalidGitRepositoryError:
            raise ValueError(f"Path is not a valid Git repository: {path}")
        
        # Create a symlink or copy to our repositories directory
        repo_id = str(uuid.uuid4())
        target_path = self.repositories_dir / repo_id
        
        # For now, we'll create a symlink (or copy on Windows)
        if os.name == 'nt':  # Windows
            shutil.copytree(str(local_path), str(target_path), symlinks=True)
        else:
            os.symlink(str(local_path), str(target_path))
        
        logger.info(f"Linked local repository {path} to {target_path}")
        return str(target_path)
    
    def get_repository_info(
        self,
        repo_path: str
    ) -> Dict[str, Any]:
        """Get information about a repository."""
        try:
            repo = Repo(repo_path)
            
            return {
                "path": repo_path,
                "active_branch": str(repo.active_branch) if repo.head.is_valid() else None,
                "remote_urls": [remote.url for remote in repo.remotes],
                "commit_count": len(list(repo.iter_commits())),
                "is_dirty": repo.is_dirty(),
            }
        except Exception as e:
            logger.error(f"Failed to get repository info: {e}")
            raise
    
    def cleanup_repository(
        self,
        repo_path: str
    ) -> None:
        """Remove a cloned repository."""
        try:
            path = Path(repo_path)
            if path.exists():
                if path.is_symlink():
                    path.unlink()
                else:
                    shutil.rmtree(str(path))
                logger.info(f"Cleaned up repository: {repo_path}")
        except Exception as e:
            logger.error(f"Failed to cleanup repository: {e}")
            raise
    
    def list_files(
        self,
        repo_path: str,
        extensions: Optional[list] = None
    ) -> list:
        """List all files in a repository."""
        path = Path(repo_path)
        files = []
        
        if extensions:
            for ext in extensions:
                files.extend(path.rglob(f"*.{ext}"))
        else:
            files = list(path.rglob("*"))
        
        # Filter out common ignore patterns
        ignore_patterns = [
            ".git",
            "__pycache__",
            "node_modules",
            ".venv",
            "venv",
            ".env",
            "dist",
            "build",
            ".next",
        ]
        
        filtered_files = []
        for file in files:
            if file.is_file():
                file_str = str(file)
                if not any(pattern in file_str for pattern in ignore_patterns):
                    filtered_files.append(str(file))
        
        return filtered_files
