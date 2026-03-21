from __future__ import annotations

import json
import uuid
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .artifact import ArtifactManifest, ReceiveProgress, VerificationResult, load_manifest, manifest_from_data


MAGIC = b"LH\x01"
FLAG_COMPRESSED_JSON = 1
MESSAGE_EXTENSION = ".lhm"
MESSAGE_TYPES = {
    "OFFER": 1,
    "SEGMENT": 2,
    "NACK_RANGES": 3,
    "COMPLETE": 4,
    "APPLY_RESULT": 5,
    "TEST": 255,
}
MESSAGE_TYPES_BY_CODE = {value: key for key, value in MESSAGE_TYPES.items()}


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


def message_filename(envelope: MessageEnvelope) -> str:
    return f"{envelope.message_id}-{envelope.message_type}{MESSAGE_EXTENSION}"


def _encode_segment_payload(payload: dict[str, Any]) -> bytes:
    artifact_id = uuid.UUID(str(payload["artifact_id"])).bytes
    index = int(payload["index"]).to_bytes(4, byteorder="big", signed=False)
    sha256 = bytes.fromhex(str(payload["sha256"]))
    data = __import__("base64").b64decode(str(payload["data"]))
    length = len(data).to_bytes(4, byteorder="big", signed=False)
    return artifact_id + index + sha256 + length + data


def _decode_segment_payload(data: bytes) -> dict[str, Any]:
    if len(data) < 56:
        raise ValueError("segment payload is truncated")
    artifact_id = str(uuid.UUID(bytes=data[:16]))
    index = int.from_bytes(data[16:20], byteorder="big", signed=False)
    sha256 = data[20:52].hex()
    length = int.from_bytes(data[52:56], byteorder="big", signed=False)
    segment_data = data[56 : 56 + length]
    if len(segment_data) != length:
        raise ValueError("segment payload length does not match header")
    return {
        "artifact_id": artifact_id,
        "index": index,
        "sha256": sha256,
        "data": __import__("base64").b64encode(segment_data).decode(),
    }


def serialize_envelope(envelope: MessageEnvelope) -> bytes:
    type_code = MESSAGE_TYPES.get(envelope.message_type)
    if type_code is None:
        raise ValueError(f"unsupported message type: {envelope.message_type}")
    if envelope.message_type == "SEGMENT":
        flags = 0
        payload = _encode_segment_payload(envelope.payload)
    else:
        flags = FLAG_COMPRESSED_JSON
        payload = zlib.compress(
            json.dumps(envelope.payload, separators=(",", ":"), sort_keys=True).encode(),
            level=9,
        )
    header = bytearray()
    header.extend(MAGIC)
    header.append(type_code)
    header.append(flags)
    header.extend(uuid.UUID(envelope.message_id).bytes)
    header.extend(len(payload).to_bytes(4, byteorder="big", signed=False))
    return bytes(header) + payload


def deserialize_envelope(data: bytes) -> MessageEnvelope:
    if data.startswith(MAGIC):
        if len(data) < 25:
            raise ValueError("message frame is truncated")
        type_code = data[3]
        flags = data[4]
        message_type = MESSAGE_TYPES_BY_CODE.get(type_code)
        if message_type is None:
            raise ValueError(f"unsupported message type code: {type_code}")
        message_id = str(uuid.UUID(bytes=data[5:21]))
        payload_length = int.from_bytes(data[21:25], byteorder="big", signed=False)
        payload_bytes = data[25 : 25 + payload_length]
        if len(payload_bytes) != payload_length:
            raise ValueError("message payload length does not match header")
        if message_type == "SEGMENT":
            payload = _decode_segment_payload(payload_bytes)
        else:
            if flags & FLAG_COMPRESSED_JSON:
                payload_bytes = zlib.decompress(payload_bytes)
            payload = json.loads(payload_bytes.decode())
            if not isinstance(payload, dict):
                raise ValueError("message payload must decode to an object")
        return MessageEnvelope(
            message_id=message_id,
            message_type=message_type,
            protocol_version=1,
            payload=payload,
        )

    decoded = json.loads(data.decode())
    if not isinstance(decoded, dict):
        raise ValueError("message envelope must be a JSON object")
    return MessageEnvelope(**decoded)


def write_envelope(path: Path, envelope: MessageEnvelope) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(serialize_envelope(envelope))
    return path


def read_envelope(path: Path) -> MessageEnvelope:
    return deserialize_envelope(path.read_bytes())


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
