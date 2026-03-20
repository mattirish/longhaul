from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import sys
from pathlib import Path

from .advertise import build_advertisement, incomplete_artifacts
from .artifact import (
    DEFAULT_SEGMENT_SIZE,
    ReceiveProgress,
    apply_artifact,
    apply_staged_artifact,
    assemble_staged_artifact,
    export_segment,
    ingest_segment,
    plan_artifact,
    stage_manifest,
    stage_artifact,
    verify_artifact,
)
from .git import GitError, current_head, ensure_repo, refs
from .messages import (
    apply_result_payload,
    complete_payload,
    manifest_from_offer_payload,
    nack_ranges_payload,
    new_envelope,
    offer_payload,
    read_envelope,
)
from .metadata import init_repo_config, load_repo_config
from .transport import (
    export_message,
    freedata_adapter,
    import_message,
    list_messages,
    read_messages,
    serialize_transport_messages,
    spool_adapter,
    summarize_messages,
)


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
        "incomplete_artifacts": incomplete_artifacts(repo_path),
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


def write_message_file(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def receive_verify_command(args: argparse.Namespace) -> int:
    verification = verify_artifact(Path(args.artifact_dir).resolve())
    print(json.dumps(asdict(verification), indent=2))
    return 0


def receive_apply_command(args: argparse.Namespace) -> int:
    repo_path = Path(args.repo).resolve()
    ensure_repo(repo_path)
    config = load_repo_config(repo_path)
    if args.artifact_id:
        manifest = apply_staged_artifact(
            repo_path,
            args.artifact_id,
            expected_repo_id=config.repo_id,
            expected_node_id=config.node_id,
        )
    else:
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
    if args.spool:
        output["spool_path"] = str(
            export_message(
                Path(args.spool).resolve(),
                new_envelope(
                    "APPLY_RESULT",
                    apply_result_payload(
                        artifact_id=manifest.artifact_id,
                        repo_id=manifest.repo_id,
                        target_ref=manifest.target_ref,
                        target_commit=manifest.target_commit,
                        receiver_node_id=manifest.receiver_node_id,
                    ),
                ),
            )
        )
    print(json.dumps(output, indent=2))
    return 0


def receive_nack_command(args: argparse.Namespace) -> int:
    repo_path = Path(args.repo).resolve()
    ensure_repo(repo_path)
    for artifact in incomplete_artifacts(repo_path):
        if artifact["artifact_id"] != args.artifact_id:
            continue
        progress = ReceiveProgress(
            artifact_id=artifact["artifact_id"],
            received_segments=artifact["received_segments"],
            missing_ranges=artifact["missing_ranges"],
            payload_verified=artifact["payload_verified"],
            applied=False,
        )
        envelope = new_envelope("NACK_RANGES", nack_ranges_payload(progress))
        output = {"artifact_id": args.artifact_id}
        if args.message:
            output["message_path"] = str(write_message_file(Path(args.message).resolve(), asdict(envelope)))
        if args.spool:
            output["spool_path"] = str(export_message(Path(args.spool).resolve(), envelope))
        if not args.message and not args.spool:
            output["message"] = asdict(envelope)
        print(json.dumps(output, indent=2))
        return 0
    raise FileNotFoundError(f"no incomplete artifact found for {args.artifact_id}")


def transport_import_command(args: argparse.Namespace) -> int:
    imported = import_message(Path(args.spool).resolve(), Path(args.message).resolve())
    print(json.dumps({"imported_path": str(imported)}, indent=2))
    return 0


def transport_list_command(args: argparse.Namespace) -> int:
    messages = summarize_messages(list_messages(Path(args.spool).resolve(), args.box))
    print(json.dumps(serialize_transport_messages(messages), indent=2))
    return 0


def transport_read_command(args: argparse.Namespace) -> int:
    print(json.dumps([asdict(envelope) for envelope in read_messages(Path(args.spool).resolve(), args.box)], indent=2))
    return 0


def transport_init_command(args: argparse.Namespace) -> int:
    if args.transport == "spool":
        adapter = spool_adapter(Path(args.root).resolve())
        adapter.ensure()
        output = {
            "transport": "spool",
            "root": str(adapter.root),
            "incoming_dir": str(adapter.incoming_dir),
            "outgoing_dir": str(adapter.outgoing_dir),
        }
    else:
        if not args.station_id or not args.peer_id:
            raise ValueError("freedata transport requires --station-id and --peer-id")
        adapter = freedata_adapter(
            Path(args.root).resolve(),
            station_id=args.station_id,
            peer_id=args.peer_id,
            api_url=args.api_url,
            host=args.host,
            cmd_port=args.cmd_port,
            data_port=args.data_port,
            bandwidth=args.bandwidth,
        )
        adapter.ensure()
        output = {
            "transport": "freedata",
            "root": str(adapter.root),
            "config_path": str(adapter.config_path),
            "mirror_incoming_dir": str(adapter.mirror.incoming_dir),
            "mirror_outgoing_dir": str(adapter.mirror.outgoing_dir),
            "host": args.host,
            "cmd_port": args.cmd_port,
            "data_port": args.data_port,
            "bandwidth": args.bandwidth,
        }
    print(json.dumps(output, indent=2))
    return 0


def transport_status_command(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    if args.transport == "spool":
        adapter = spool_adapter(root)
        adapter.ensure()
        output = {
            "transport": "spool",
            "root": str(adapter.root),
            "incoming_count": len(adapter.list("incoming")),
            "outgoing_count": len(adapter.list("outgoing")),
        }
    else:
        adapter = freedata_adapter(
            root,
            station_id=args.station_id or "unknown",
            peer_id=args.peer_id or "unknown",
            api_url=args.api_url,
            host=args.host,
            cmd_port=args.cmd_port,
            data_port=args.data_port,
            bandwidth=args.bandwidth,
        )
        adapter.ensure()
        output = {
            "transport": "freedata",
            "root": str(adapter.root),
            "config_path": str(adapter.config_path),
            "mirror_incoming_count": len(adapter.list("incoming")),
            "mirror_outgoing_count": len(adapter.list("outgoing")),
            "host": args.host,
            "cmd_port": args.cmd_port,
            "data_port": args.data_port,
            "bandwidth": args.bandwidth,
        }
    print(json.dumps(output, indent=2))
    return 0


def transport_probe_command(args: argparse.Namespace) -> int:
    if args.transport != "freedata":
        raise ValueError("probe is only implemented for the freedata transport")
    adapter = freedata_adapter(
        Path(args.root).resolve(),
        station_id=args.station_id,
        peer_id=args.peer_id,
        api_url=args.api_url,
        host=args.host,
        cmd_port=args.cmd_port,
        data_port=args.data_port,
        bandwidth=args.bandwidth,
    )
    adapter.ensure()
    version = adapter.socket_config
    from .freedata import FreeDataCommandClient

    responses = FreeDataCommandClient(version).version()
    print(
        json.dumps(
            {
                "transport": "freedata",
                "host": args.host,
                "cmd_port": args.cmd_port,
                "responses": responses,
            },
            indent=2,
        )
    )
    return 0


def transport_dispatch_command(args: argparse.Namespace) -> int:
    message = read_envelope(Path(args.message).resolve())
    if args.transport == "spool":
        path = export_message(Path(args.root).resolve(), message)
        print(json.dumps({"transport": "spool", "dispatched_path": str(path)}, indent=2))
        return 0

    adapter = freedata_adapter(
        Path(args.root).resolve(),
        station_id=args.station_id,
        peer_id=args.peer_id,
        api_url=args.api_url,
        host=args.host,
        cmd_port=args.cmd_port,
        data_port=args.data_port,
        bandwidth=args.bandwidth,
    )
    path = adapter.send(message)
    print(
        json.dumps(
            {
                "transport": "freedata",
                "mirror_path": str(path),
                "message_id": message.message_id,
                "message_type": message.message_type,
            },
            indent=2,
        )
    )
    return 0


def send_segment_command(args: argparse.Namespace) -> int:
    output_path = export_segment(
        Path(args.artifact_dir).resolve(),
        args.index,
        Path(args.output).resolve(),
    )
    result = {"segment_path": str(output_path), "index": args.index}
    if args.spool:
        envelope = new_envelope("SEGMENT", json.loads(output_path.read_text()))
        spool_path = export_message(Path(args.spool).resolve(), envelope)
        result["spool_path"] = str(spool_path)
    print(json.dumps(result, indent=2))
    return 0


def send_offer_command(args: argparse.Namespace) -> int:
    envelope = new_envelope("OFFER", offer_payload(Path(args.manifest).resolve()))
    result = {"message_id": envelope.message_id, "message_type": envelope.message_type}
    if args.message:
        message_path = write_message_file(Path(args.message).resolve(), asdict(envelope))
        result["message_path"] = str(message_path)
    if args.spool:
        result["spool_path"] = str(export_message(Path(args.spool).resolve(), envelope))
    print(json.dumps(result, indent=2))
    return 0


def receive_offer_command(args: argparse.Namespace) -> int:
    repo_path = Path(args.repo).resolve()
    ensure_repo(repo_path)
    config = load_repo_config(repo_path)
    if args.message:
        envelope = read_envelope(Path(args.message).resolve())
        if envelope.message_type != "OFFER":
            raise ValueError("message is not an OFFER")
        progress = stage_manifest(
            repo_path,
            manifest_from_offer_payload(envelope.payload),
            expected_repo_id=config.repo_id,
            expected_node_id=config.node_id,
        )
    else:
        progress = stage_artifact(
            repo_path,
            Path(args.manifest).resolve(),
            expected_repo_id=config.repo_id,
            expected_node_id=config.node_id,
        )
    print(json.dumps(asdict(progress), indent=2))
    return 0


def receive_segment_command(args: argparse.Namespace) -> int:
    repo_path = Path(args.repo).resolve()
    ensure_repo(repo_path)
    artifact_id = args.artifact_id
    segment_path = Path(args.segment).resolve() if args.segment else None
    if args.message:
        envelope = read_envelope(Path(args.message).resolve())
        if envelope.message_type != "SEGMENT":
            raise ValueError("message is not a SEGMENT")
        payload_artifact_id = envelope.payload.get("artifact_id")
        if not isinstance(payload_artifact_id, str):
            raise ValueError("segment message missing artifact_id")
        artifact_id = payload_artifact_id
        segment_path = write_message_file(
            repo_path / ".longhaul" / "tmp" / f"{envelope.message_id}.segment.json",
            envelope.payload,
        )
    if artifact_id is None or segment_path is None:
        raise ValueError("segment input is incomplete")
    progress = ingest_segment(
        repo_path,
        artifact_id,
        segment_path,
    )
    print(json.dumps(asdict(progress), indent=2))
    return 0


def receive_complete_command(args: argparse.Namespace) -> int:
    repo_path = Path(args.repo).resolve()
    ensure_repo(repo_path)
    verification = assemble_staged_artifact(repo_path, args.artifact_id)
    result = asdict(verification)
    if args.spool:
        result["spool_path"] = str(
            export_message(
                Path(args.spool).resolve(),
                new_envelope("COMPLETE", complete_payload(verification)),
            )
        )
    print(json.dumps(result, indent=2))
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

    send_parser = subparsers.add_parser("send")
    send_subparsers = send_parser.add_subparsers(dest="send_command", required=True)

    send_offer_parser = send_subparsers.add_parser("offer")
    send_offer_parser.add_argument("--manifest", required=True)
    send_offer_parser.add_argument("--message")
    send_offer_parser.add_argument("--spool")
    send_offer_parser.set_defaults(func=send_offer_command)

    send_segment_parser = send_subparsers.add_parser("segment")
    send_segment_parser.add_argument("--artifact-dir", required=True)
    send_segment_parser.add_argument("--index", type=int, required=True)
    send_segment_parser.add_argument("--output", required=True)
    send_segment_parser.add_argument("--spool")
    send_segment_parser.set_defaults(func=send_segment_command)

    receive_parser = subparsers.add_parser("receive")
    receive_subparsers = receive_parser.add_subparsers(dest="receive_command", required=True)

    offer_parser = receive_subparsers.add_parser("offer")
    offer_parser.add_argument("--repo", default=".")
    offer_group = offer_parser.add_mutually_exclusive_group(required=True)
    offer_group.add_argument("--manifest")
    offer_group.add_argument("--message")
    offer_parser.set_defaults(func=receive_offer_command)

    segment_parser = receive_subparsers.add_parser("segment")
    segment_parser.add_argument("--repo", default=".")
    segment_parser.add_argument("--artifact-id")
    segment_group = segment_parser.add_mutually_exclusive_group(required=True)
    segment_group.add_argument("--segment")
    segment_group.add_argument("--message")
    segment_parser.set_defaults(func=receive_segment_command)

    complete_parser = receive_subparsers.add_parser("complete")
    complete_parser.add_argument("--repo", default=".")
    complete_parser.add_argument("--artifact-id", required=True)
    complete_parser.add_argument("--spool")
    complete_parser.set_defaults(func=receive_complete_command)

    verify_parser = receive_subparsers.add_parser("verify")
    verify_parser.add_argument("--artifact-dir", required=True)
    verify_parser.set_defaults(func=receive_verify_command)

    apply_parser = receive_subparsers.add_parser("apply")
    apply_parser.add_argument("--repo", default=".")
    apply_group = apply_parser.add_mutually_exclusive_group(required=True)
    apply_group.add_argument("--artifact-dir")
    apply_group.add_argument("--artifact-id")
    apply_parser.add_argument("--spool")
    apply_parser.set_defaults(func=receive_apply_command)

    nack_parser = receive_subparsers.add_parser("nack")
    nack_parser.add_argument("--repo", default=".")
    nack_parser.add_argument("--artifact-id", required=True)
    nack_parser.add_argument("--message")
    nack_parser.add_argument("--spool")
    nack_parser.set_defaults(func=receive_nack_command)

    transport_parser = subparsers.add_parser("transport")
    transport_subparsers = transport_parser.add_subparsers(dest="transport_command", required=True)

    transport_init_parser = transport_subparsers.add_parser("init")
    transport_init_parser.add_argument("--transport", choices=["spool", "freedata"], default="spool")
    transport_init_parser.add_argument("--root", required=True)
    transport_init_parser.add_argument("--station-id")
    transport_init_parser.add_argument("--peer-id")
    transport_init_parser.add_argument("--api-url")
    transport_init_parser.add_argument("--host", default="127.0.0.1")
    transport_init_parser.add_argument("--cmd-port", type=int, default=9000)
    transport_init_parser.add_argument("--data-port", type=int, default=9001)
    transport_init_parser.add_argument("--bandwidth", type=int, default=2300)
    transport_init_parser.set_defaults(func=transport_init_command)

    transport_status_parser = transport_subparsers.add_parser("status")
    transport_status_parser.add_argument("--transport", choices=["spool", "freedata"], default="spool")
    transport_status_parser.add_argument("--root", required=True)
    transport_status_parser.add_argument("--station-id")
    transport_status_parser.add_argument("--peer-id")
    transport_status_parser.add_argument("--api-url")
    transport_status_parser.add_argument("--host", default="127.0.0.1")
    transport_status_parser.add_argument("--cmd-port", type=int, default=9000)
    transport_status_parser.add_argument("--data-port", type=int, default=9001)
    transport_status_parser.add_argument("--bandwidth", type=int, default=2300)
    transport_status_parser.set_defaults(func=transport_status_command)

    transport_import_parser = transport_subparsers.add_parser("import")
    transport_import_parser.add_argument("--spool", required=True)
    transport_import_parser.add_argument("--message", required=True)
    transport_import_parser.set_defaults(func=transport_import_command)

    transport_list_parser = transport_subparsers.add_parser("list")
    transport_list_parser.add_argument("--spool", required=True)
    transport_list_parser.add_argument("--box", choices=["incoming", "outgoing"], default="incoming")
    transport_list_parser.set_defaults(func=transport_list_command)

    transport_read_parser = transport_subparsers.add_parser("read")
    transport_read_parser.add_argument("--spool", required=True)
    transport_read_parser.add_argument("--box", choices=["incoming", "outgoing"], default="incoming")
    transport_read_parser.set_defaults(func=transport_read_command)

    transport_probe_parser = transport_subparsers.add_parser("probe")
    transport_probe_parser.add_argument("--transport", choices=["freedata"], default="freedata")
    transport_probe_parser.add_argument("--root", required=True)
    transport_probe_parser.add_argument("--station-id", required=True)
    transport_probe_parser.add_argument("--peer-id", required=True)
    transport_probe_parser.add_argument("--api-url")
    transport_probe_parser.add_argument("--host", default="127.0.0.1")
    transport_probe_parser.add_argument("--cmd-port", type=int, default=9000)
    transport_probe_parser.add_argument("--data-port", type=int, default=9001)
    transport_probe_parser.add_argument("--bandwidth", type=int, default=2300)
    transport_probe_parser.set_defaults(func=transport_probe_command)

    transport_dispatch_parser = transport_subparsers.add_parser("dispatch")
    transport_dispatch_parser.add_argument("--transport", choices=["spool", "freedata"], default="spool")
    transport_dispatch_parser.add_argument("--root", required=True)
    transport_dispatch_parser.add_argument("--message", required=True)
    transport_dispatch_parser.add_argument("--station-id")
    transport_dispatch_parser.add_argument("--peer-id")
    transport_dispatch_parser.add_argument("--api-url")
    transport_dispatch_parser.add_argument("--host", default="127.0.0.1")
    transport_dispatch_parser.add_argument("--cmd-port", type=int, default=9000)
    transport_dispatch_parser.add_argument("--data-port", type=int, default=9001)
    transport_dispatch_parser.add_argument("--bandwidth", type=int, default=2300)
    transport_dispatch_parser.set_defaults(func=transport_dispatch_command)

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
