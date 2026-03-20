from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .advertise import build_advertisement
from .git import GitError, current_head, ensure_repo, refs
from .metadata import init_repo_config, load_receive_state, load_repo_config


def repo_init(args: argparse.Namespace) -> int:
    repo_path = Path(args.repo).resolve()
    ensure_repo(repo_path)
    config = init_repo_config(
        repo_path,
        node_id=args.node_id,
        repo_id=args.repo_id,
        force=args.force,
    )
    print(json.dumps({"repo_id": config.repo_id, "node_id": config.node_id}, indent=2))
    return 0


def repo_status(args: argparse.Namespace) -> int:
    repo_path = Path(args.repo).resolve()
    ensure_repo(repo_path)
    config = load_repo_config(repo_path)
    data = {
        "repo_id": config.repo_id,
        "node_id": config.node_id,
        "head": current_head(repo_path),
        "refs": refs(repo_path),
        "incomplete_artifacts": load_receive_state(repo_path),
    }
    print(json.dumps(data, indent=2))
    return 0


def repo_advertise(args: argparse.Namespace) -> int:
    repo_path = Path(args.repo).resolve()
    ensure_repo(repo_path)
    print(json.dumps(build_advertisement(repo_path), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="longhaul")
    subparsers = parser.add_subparsers(dest="command", required=True)

    repo_parser = subparsers.add_parser("repo")
    repo_subparsers = repo_parser.add_subparsers(dest="repo_command", required=True)

    init_parser = repo_subparsers.add_parser("init")
    init_parser.add_argument("--repo", default=".")
    init_parser.add_argument("--node-id", required=True)
    init_parser.add_argument("--repo-id")
    init_parser.add_argument("--force", action="store_true")
    init_parser.set_defaults(func=repo_init)

    status_parser = repo_subparsers.add_parser("status")
    status_parser.add_argument("--repo", default=".")
    status_parser.set_defaults(func=repo_status)

    advertise_parser = repo_subparsers.add_parser("advertise")
    advertise_parser.add_argument("--repo", default=".")
    advertise_parser.set_defaults(func=repo_advertise)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except (GitError, FileNotFoundError, FileExistsError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
