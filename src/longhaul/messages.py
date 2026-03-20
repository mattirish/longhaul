from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .artifact import ArtifactManifest, ReceiveProgress, VerificationResult, load_manifest, manifest_from_data


@dataclass
class MessageEnvelope:
    message_id: str
    message_type: str
    protocol_version: int
    payload: dict[str, Any]


def new_envelope(message_type: str, payload: dict[str, Any], *, protocol_version: int = 1) -> MessageEnvelope:
    return MessageEnvelope(
        message_id=str(uuid.uuid4()),
        message_type=message_type,
        protocol_version=protocol_version,
        payload=payload,
    )


def write_envelope(path: Path, envelope: MessageEnvelope) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(envelope), indent=2) + "\n")
    return path


def read_envelope(path: Path) -> MessageEnvelope:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("message envelope must be a JSON object")
    return MessageEnvelope(**data)


def offer_payload(manifest_path: Path) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    return {
        "artifact_id": manifest.artifact_id,
        "repo_id": manifest.repo_id,
        "sender_node_id": manifest.sender_node_id,
        "receiver_node_id": manifest.receiver_node_id,
        "baseline_commit": manifest.baseline_commit,
        "target_ref": manifest.target_ref,
        "target_commit": manifest.target_commit,
        "payload_size": manifest.payload_size,
        "segment_size": manifest.segment_size,
        "segment_count": manifest.segment_count,
        "payload_sha256": manifest.payload_sha256,
        "manifest": asdict(manifest),
    }


def manifest_from_offer_payload(payload: dict[str, Any]) -> ArtifactManifest:
    manifest = payload.get("manifest")
    if not isinstance(manifest, dict):
        raise ValueError("offer payload must include a manifest object")
    return manifest_from_data(manifest)


def nack_ranges_payload(progress: ReceiveProgress) -> dict[str, Any]:
    return {
        "artifact_id": progress.artifact_id,
        "missing_ranges": progress.missing_ranges,
        "received_segments": progress.received_segments,
        "payload_verified": progress.payload_verified,
        "applied": progress.applied,
    }


def complete_payload(verification: VerificationResult) -> dict[str, Any]:
    return {
        "artifact_id": verification.artifact_id,
        "payload_size": verification.payload_size,
        "payload_sha256": verification.payload_sha256,
        "segment_count": verification.segment_count,
        "verification_status": "ok",
    }


def apply_result_payload(
    *,
    artifact_id: str,
    repo_id: str,
    target_ref: str,
    target_commit: str,
    receiver_node_id: str,
) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "repo_id": repo_id,
        "target_ref": target_ref,
        "target_commit": target_commit,
        "receiver_node_id": receiver_node_id,
        "apply_status": "ok",
    }
