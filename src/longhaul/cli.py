from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .advertise import build_advertisement
from .artifact import DEFAULT_SEGMENT_SIZE, apply_artifact, plan_artifact, verify_artifact
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


def plan_artifact_command(args: argparse.Namespace) -> int:
    repo_path = Path(args.repo).resolve()
    ensure_repo(repo_path)
    config = load_repo_config(repo_path)
    manifest = plan_artifact(
        repo_path,
        Path(args.advertisement).resolve(),
        args.target_ref,
        Path(args.output_dir).resolve(),
        expected_repo_id=config.repo_id,
        sender_node_id=config.node_id,
        baseline_ref=args.baseline_ref,
        segment_size=args.segment_size,
    )
    output = {
        "artifact_id": manifest.artifact_id,
        "repo_id": manifest.repo_id,
        "sender_node_id": config.node_id,
        "receiver_node_id": manifest.receiver_node_id,
        "baseline_commit": manifest.baseline_commit,
        "target_ref": manifest.target_ref,
        "target_commit": manifest.target_commit,
        "payload_size": manifest.payload_size,
        "object_count": manifest.object_count,
        "segment_count": manifest.segment_count,
        "manifest_path": str(Path(args.output_dir).resolve() / manifest.artifact_id / "manifest.json"),
    }
    print(json.dumps(output, indent=2))
    return 0


def receive_verify_command(args: argparse.Namespace) -> int:
    verification = verify_artifact(Path(args.artifact_dir).resolve())
    print(json.dumps(verification.__dict__, indent=2))
    return 0


def receive_apply_command(args: argparse.Namespace) -> int:
    repo_path = Path(args.repo).resolve()
    ensure_repo(repo_path)
    config = load_repo_config(repo_path)
    manifest = apply_artifact(
        repo_path,
        Path(args.artifact_dir).resolve(),
        expected_repo_id=config.repo_id,
        expected_node_id=config.node_id,
    )
    output = {
        "artifact_id": manifest.artifact_id,
        "repo_id": manifest.repo_id,
        "target_ref": manifest.target_ref,
        "target_commit": manifest.target_commit,
        "receiver_node_id": manifest.receiver_node_id,
    }
    print(json.dumps(output, indent=2))
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

    plan_parser = subparsers.add_parser("plan")
    plan_subparsers = plan_parser.add_subparsers(dest="plan_command", required=True)

    artifact_parser = plan_subparsers.add_parser("artifact")
    artifact_parser.add_argument("--repo", default=".")
    artifact_parser.add_argument("--advertisement", required=True)
    artifact_parser.add_argument("--target-ref", required=True)
    artifact_parser.add_argument("--output-dir", required=True)
    artifact_parser.add_argument("--baseline-ref")
    artifact_parser.add_argument("--segment-size", type=int, default=DEFAULT_SEGMENT_SIZE)
    artifact_parser.set_defaults(func=plan_artifact_command)

    receive_parser = subparsers.add_parser("receive")
    receive_subparsers = receive_parser.add_subparsers(dest="receive_command", required=True)

    verify_parser = receive_subparsers.add_parser("verify")
    verify_parser.add_argument("--artifact-dir", required=True)
    verify_parser.set_defaults(func=receive_verify_command)

    apply_parser = receive_subparsers.add_parser("apply")
    apply_parser.add_argument("--repo", default=".")
    apply_parser.add_argument("--artifact-dir", required=True)
    apply_parser.set_defaults(func=receive_apply_command)

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
