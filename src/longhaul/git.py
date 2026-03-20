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


def rev_parse(repo_path: Path, ref: str) -> str:
    return run_git(repo_path, "rev-parse", ref)


def rev_parse_optional(repo_path: Path, ref: str) -> str | None:
    try:
        return rev_parse(repo_path, ref)
    except GitError:
        return None


def canonical_ref(repo_path: Path, ref: str) -> str:
    try:
        return run_git(repo_path, "symbolic-ref", "-q", ref)
    except GitError:
        return ref


def object_closure(repo_path: Path, target: str, baseline: str | None = None) -> list[str]:
    args = ["rev-list", "--objects", target]
    if baseline:
        args.append(f"^{baseline}")
    output = run_git(repo_path, *args)
    if not output:
        return []

    objects: list[str] = []
    for line in output.splitlines():
        oid = line.split(" ", 1)[0]
        objects.append(oid)
    return objects


def pack_objects(repo_path: Path, object_ids: list[str], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not object_ids:
        output_path.write_bytes(b"")
        return

    result = subprocess.run(
        ["git", "pack-objects", "--compression=9", "--stdout"],
        cwd=repo_path,
        input="".join(f"{oid}\n" for oid in object_ids).encode(),
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        stdout = result.stdout.decode(errors="replace").strip()
        raise GitError(stderr or stdout or "git pack-objects failed")
    output_path.write_bytes(result.stdout)


def unpack_objects(repo_path: Path, pack_path: Path) -> None:
    result = subprocess.run(
        ["git", "unpack-objects"],
        cwd=repo_path,
        input=pack_path.read_bytes(),
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        stdout = result.stdout.decode(errors="replace").strip()
        raise GitError(stderr or stdout or "git unpack-objects failed")


def object_exists(repo_path: Path, object_id: str, kind: str | None = None) -> bool:
    spec = f"{object_id}^{{{kind}}}" if kind else object_id
    result = subprocess.run(
        ["git", "cat-file", "-e", spec],
        cwd=repo_path,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def update_ref(repo_path: Path, ref: str, new_value: str, old_value: str | None = None) -> None:
    args = ["update-ref", ref, new_value]
    if old_value is not None:
        args.append(old_value)
    run_git(repo_path, *args)
