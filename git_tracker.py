"""Git-based SQL file discovery helpers for local mode.

This module is used by cli.py preview/diff/publish commands when running outside
PR mode to list changed SQL files from a configured git diff range.
"""

from pathlib import Path
from typing import List, Optional

from git import InvalidGitRepositoryError, Repo


def list_changed_sql_files(repo_root: Path, diff_range: Optional[str] = None) -> List[Path]:
    repo_root = Path(repo_root).resolve()
    try:
        repo = Repo(repo_root)
    except InvalidGitRepositoryError as exc:
        raise ValueError(f"Path is not a git repository: {repo_root}") from exc

    diff_range = diff_range or "HEAD~1..HEAD"
    diff_text = repo.git.diff("--name-only", diff_range)
    files = [Path(repo_root / p) for p in diff_text.splitlines() if p.strip() and p.strip().lower().endswith(".sql")]
    return [f for f in files if f.exists()]


def find_sql_files(repo_root: Path, glob_pattern: str) -> List[Path]:
    repo_root = Path(repo_root).resolve()
    return sorted(repo_root.glob(glob_pattern))
