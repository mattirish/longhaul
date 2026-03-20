from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    """Raised when a Git command fails."""


def run_git(repo_path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise GitError(result.stderr.strip() or result.stdout.strip() or "git command failed")
    return result.stdout.strip()


def ensure_repo(repo_path: Path) -> None:
    git_dir = repo_path / ".git"
    if not git_dir.exists():
        raise GitError(f"{repo_path} is not a Git repository")


def current_head(repo_path: Path) -> str | None:
    try:
        return run_git(repo_path, "rev-parse", "HEAD")
    except GitError:
        return None


def refs(repo_path: Path) -> dict[str, str]:
    output = run_git(repo_path, "for-each-ref", "--format=%(objectname) %(refname)")
    refs: dict[str, str] = {}
    if not output:
        return refs
    for line in output.splitlines():
        sha, ref = line.split(" ", 1)
        refs[ref] = sha
    return refs
