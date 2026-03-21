from __future__ import annotations

import hashlib
import json
import math
import uuid
from base64 import b64decode, b64encode
from dataclasses import asdict, dataclass
from itertools import groupby
from pathlib import Path

from .git import canonical_ref, create_bundle, import_bundle, object_closure, object_exists, rev_parse, rev_parse_optional, update_ref
from .metadata import (
    ReceiveArtifactState,
    artifact_incoming_dir,
    artifact_segment_dir,
    get_receive_artifact_state,
    upsert_receive_artifact_state,
)


DEFAULT_SEGMENT_SIZE = 4096


@dataclass
class Segment:
    index: int
    offset: int
    length: int
    sha256: str


@dataclass
class ArtifactManifest:
    protocol_version: int
    artifact_id: str
    repo_id: str
    sender_node_id: str
    receiver_node_id: str
    baseline_commit: str | None
    target_ref: str
    target_commit: str
    payload_path: str
    payload_size: int
    object_count: int
    segment_size: int
    segment_count: int
    payload_sha256: str
    segments: list[Segment]


@dataclass
class VerificationResult:
    artifact_id: str
    payload_size: int
    payload_sha256: str
    segment_count: int


@dataclass
class ReceiveProgress:
    artifact_id: str
    received_segments: list[int]
    missing_ranges: list[list[int]]
    payload_verified: bool
    applied: bool


def load_advertisement(path: Path) -> dict:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("advertisement must be a JSON object")
    return data


def baseline_for_target(advertisement: dict, target_ref: str, baseline_ref: str | None) -> str | None:
    refs = advertisement.get("refs", {})
    if not isinstance(refs, dict):
        raise ValueError("advertisement refs must be an object")

    selected_ref = baseline_ref or target_ref
    value = refs.get(selected_ref)
    if value is not None and not isinstance(value, str):
        raise ValueError("baseline ref value must be a string")
    return value if value else advertisement.get("head")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def segment_manifest(payload_path: Path, segment_size: int) -> list[Segment]:
    payload = payload_path.read_bytes()
    if not payload:
        return []

    count = math.ceil(len(payload) / segment_size)
    segments: list[Segment] = []
    for index in range(count):
        offset = index * segment_size
        chunk = payload[offset : offset + segment_size]
        segments.append(
            Segment(
                index=index,
                offset=offset,
                length=len(chunk),
                sha256=hashlib.sha256(chunk).hexdigest(),
            )
        )
    return segments


def write_manifest(output_dir: Path, manifest: ArtifactManifest) -> Path:
    path = output_dir / "manifest.json"
    serialized = asdict(manifest)
    serialized["segments"] = [asdict(segment) for segment in manifest.segments]
    path.write_text(json.dumps(serialized, indent=2) + "\n")
    return path


def load_manifest(path: Path) -> ArtifactManifest:
    data = json.loads(path.read_text())
    return manifest_from_data(data)


def manifest_from_data(data: dict) -> ArtifactManifest:
    if not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object")
    segments = data.get("segments", [])
    if not isinstance(segments, list):
        raise ValueError("manifest segments must be a list")
    data["segments"] = [Segment(**segment) for segment in segments]
    return ArtifactManifest(**data)


def manifest_from_dir(artifact_dir: Path) -> ArtifactManifest:
    return load_manifest(artifact_dir / "manifest.json")


def plan_artifact(
    repo_path: Path,
    advertisement_path: Path,
    target_ref: str,
    output_dir: Path,
    *,
    expected_repo_id: str,
    sender_node_id: str,
    baseline_ref: str | None = None,
    segment_size: int = DEFAULT_SEGMENT_SIZE,
) -> ArtifactManifest:
    advertisement = load_advertisement(advertisement_path)
    repo_id = advertisement.get("repo_id")
    receiver_node_id = advertisement.get("node_id")
    if not isinstance(repo_id, str) or not isinstance(receiver_node_id, str):
        raise ValueError("advertisement must include string repo_id and node_id")
    if repo_id != expected_repo_id:
        raise ValueError("advertisement repo_id does not match local Longhaul repository ID")

    resolved_target_ref = canonical_ref(repo_path, target_ref)
    target_commit = rev_parse(repo_path, target_ref)
    baseline_commit = baseline_for_target(advertisement, target_ref, baseline_ref)
    object_ids = object_closure(repo_path, target_commit, baseline_commit)

    artifact_id = str(uuid.uuid4())
    artifact_dir = output_dir / artifact_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    payload_path = artifact_dir / "payload.bundle"
    create_bundle(repo_path, payload_path, resolved_target_ref, baseline_commit)

    segments = segment_manifest(payload_path, segment_size)
    payload_size = payload_path.stat().st_size

    manifest = ArtifactManifest(
        protocol_version=1,
        artifact_id=artifact_id,
        repo_id=repo_id,
        sender_node_id=sender_node_id,
        receiver_node_id=receiver_node_id,
        baseline_commit=baseline_commit,
        target_ref=resolved_target_ref,
        target_commit=target_commit,
        payload_path=str(payload_path.relative_to(artifact_dir)),
        payload_size=payload_size,
        object_count=len(object_ids),
        segment_size=segment_size,
        segment_count=len(segments),
        payload_sha256=sha256_file(payload_path),
        segments=segments,
    )
    write_manifest(artifact_dir, manifest)
    return manifest


def payload_path_for_manifest(artifact_dir: Path, manifest: ArtifactManifest) -> Path:
    return artifact_dir / manifest.payload_path


def segment_by_index(manifest: ArtifactManifest, index: int) -> Segment:
    if index < 0 or index >= len(manifest.segments):
        raise ValueError(f"segment index {index} is out of range")
    return manifest.segments[index]


def missing_ranges(segment_count: int, received_segments: list[int]) -> list[list[int]]:
    missing = sorted(set(range(segment_count)) - set(received_segments))
    ranges: list[list[int]] = []
    for _, group in groupby(enumerate(missing), lambda pair: pair[1] - pair[0]):
        numbers = [item[1] for item in group]
        ranges.append([numbers[0], numbers[-1]])
    return ranges


def extract_segment(artifact_dir: Path, index: int) -> bytes:
    manifest = manifest_from_dir(artifact_dir)
    segment = segment_by_index(manifest, index)
    payload_path = payload_path_for_manifest(artifact_dir, manifest)
    with payload_path.open("rb") as handle:
        handle.seek(segment.offset)
        return handle.read(segment.length)


def export_segment(artifact_dir: Path, index: int, output_path: Path) -> Path:
    manifest = manifest_from_dir(artifact_dir)
    segment = segment_by_index(manifest, index)
    payload = extract_segment(artifact_dir, index)
    if len(payload) != segment.length:
        raise ValueError("segment length does not match manifest")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    envelope = {
        "artifact_id": manifest.artifact_id,
        "index": index,
        "sha256": segment.sha256,
        "data": b64encode(payload).decode(),
    }
    output_path.write_text(json.dumps(envelope, indent=2) + "\n")
    return output_path


def stage_artifact(repo_path: Path, manifest_path: Path, *, expected_repo_id: str, expected_node_id: str) -> ReceiveProgress:
    manifest = load_manifest(manifest_path)
    return stage_manifest(repo_path, manifest, expected_repo_id=expected_repo_id, expected_node_id=expected_node_id)


def stage_manifest(
    repo_path: Path,
    manifest: ArtifactManifest,
    *,
    expected_repo_id: str,
    expected_node_id: str,
) -> ReceiveProgress:
    if manifest.repo_id != expected_repo_id:
        raise ValueError("artifact repo_id does not match local Longhaul repository ID")
    if manifest.receiver_node_id != expected_node_id:
        raise ValueError("artifact receiver_node_id does not match local Longhaul node ID")

    artifact_dir = artifact_incoming_dir(repo_path, manifest.artifact_id)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_segment_dir(repo_path, manifest.artifact_id).mkdir(exist_ok=True)
    write_manifest(artifact_dir, manifest)

    state = ReceiveArtifactState(
        artifact_id=manifest.artifact_id,
        sender_node_id=manifest.sender_node_id,
        receiver_node_id=manifest.receiver_node_id,
        target_ref=manifest.target_ref,
        target_commit=manifest.target_commit,
        segment_count=manifest.segment_count,
        received_segments=[],
        payload_verified=False,
        applied=False,
    )
    upsert_receive_artifact_state(repo_path, state)
    return ReceiveProgress(
        artifact_id=state.artifact_id,
        received_segments=state.received_segments,
        missing_ranges=missing_ranges(state.segment_count, state.received_segments),
        payload_verified=state.payload_verified,
        applied=state.applied,
    )


def ingest_segment(repo_path: Path, artifact_id: str, segment_path: Path) -> ReceiveProgress:
    state = get_receive_artifact_state(repo_path, artifact_id)
    artifact_dir = artifact_incoming_dir(repo_path, artifact_id)
    manifest = manifest_from_dir(artifact_dir)

    envelope = json.loads(segment_path.read_text())
    if not isinstance(envelope, dict):
        raise ValueError("segment envelope must be a JSON object")
    if envelope.get("artifact_id") != artifact_id:
        raise ValueError("segment artifact_id does not match requested artifact")
    index = envelope.get("index")
    if not isinstance(index, int):
        raise ValueError("segment index must be an integer")
    payload_encoded = envelope.get("data")
    if not isinstance(payload_encoded, str):
        raise ValueError("segment data must be a string")

    segment = segment_by_index(manifest, index)
    payload = b64decode(payload_encoded)
    if len(payload) != segment.length:
        raise ValueError("segment payload length does not match manifest")
    payload_sha256 = hashlib.sha256(payload).hexdigest()
    if payload_sha256 != segment.sha256:
        raise ValueError("segment payload hash does not match manifest")

    segment_output_path = artifact_segment_dir(repo_path, artifact_id) / f"{index:08d}.seg"
    segment_output_path.write_bytes(payload)

    received = sorted(set(state.received_segments) | {index})
    updated_state = ReceiveArtifactState(
        artifact_id=state.artifact_id,
        sender_node_id=state.sender_node_id,
        receiver_node_id=state.receiver_node_id,
        target_ref=state.target_ref,
        target_commit=state.target_commit,
        segment_count=state.segment_count,
        received_segments=received,
        payload_verified=False,
        applied=state.applied,
    )
    upsert_receive_artifact_state(repo_path, updated_state)
    return ReceiveProgress(
        artifact_id=updated_state.artifact_id,
        received_segments=updated_state.received_segments,
        missing_ranges=missing_ranges(updated_state.segment_count, updated_state.received_segments),
        payload_verified=updated_state.payload_verified,
        applied=updated_state.applied,
    )


def assemble_staged_artifact(repo_path: Path, artifact_id: str) -> VerificationResult:
    state = get_receive_artifact_state(repo_path, artifact_id)
    missing = missing_ranges(state.segment_count, state.received_segments)
    if missing:
        raise ValueError(f"artifact is incomplete; missing ranges: {missing}")

    artifact_dir = artifact_incoming_dir(repo_path, artifact_id)
    manifest = manifest_from_dir(artifact_dir)
    payload_path = payload_path_for_manifest(artifact_dir, manifest)
    payload_path.parent.mkdir(parents=True, exist_ok=True)

    with payload_path.open("wb") as output:
        for segment in manifest.segments:
            segment_path = artifact_segment_dir(repo_path, artifact_id) / f"{segment.index:08d}.seg"
            if not segment_path.exists():
                raise FileNotFoundError(f"missing staged segment: {segment_path}")
            data = segment_path.read_bytes()
            if len(data) != segment.length:
                raise ValueError("staged segment length does not match manifest")
            if hashlib.sha256(data).hexdigest() != segment.sha256:
                raise ValueError("staged segment hash does not match manifest")
            output.write(data)

    verification = verify_artifact(artifact_dir)
    updated_state = ReceiveArtifactState(
        artifact_id=state.artifact_id,
        sender_node_id=state.sender_node_id,
        receiver_node_id=state.receiver_node_id,
        target_ref=state.target_ref,
        target_commit=state.target_commit,
        segment_count=state.segment_count,
        received_segments=state.received_segments,
        payload_verified=True,
        applied=state.applied,
    )
    upsert_receive_artifact_state(repo_path, updated_state)
    return verification


def verify_artifact(artifact_dir: Path) -> VerificationResult:
    manifest = manifest_from_dir(artifact_dir)
    payload_path = payload_path_for_manifest(artifact_dir, manifest)
    if not payload_path.exists():
        raise FileNotFoundError(f"artifact payload is missing: {payload_path}")

    payload_size = payload_path.stat().st_size
    if payload_size != manifest.payload_size:
        raise ValueError("artifact payload size does not match manifest")

    payload_sha256 = sha256_file(payload_path)
    if payload_sha256 != manifest.payload_sha256:
        raise ValueError("artifact payload hash does not match manifest")

    segments = segment_manifest(payload_path, manifest.segment_size)
    if len(segments) != manifest.segment_count:
        raise ValueError("artifact segment count does not match manifest")

    expected_segments = [asdict(segment) for segment in manifest.segments]
    actual_segments = [asdict(segment) for segment in segments]
    if actual_segments != expected_segments:
        raise ValueError("artifact segment hashes do not match manifest")

    return VerificationResult(
        artifact_id=manifest.artifact_id,
        payload_size=payload_size,
        payload_sha256=payload_sha256,
        segment_count=len(segments),
    )


def apply_artifact(repo_path: Path, artifact_dir: Path, *, expected_repo_id: str, expected_node_id: str) -> ArtifactManifest:
    manifest = manifest_from_dir(artifact_dir)
    if manifest.repo_id != expected_repo_id:
        raise ValueError("artifact repo_id does not match local Longhaul repository ID")
    if manifest.receiver_node_id != expected_node_id:
        raise ValueError("artifact receiver_node_id does not match local Longhaul node ID")

    verify_artifact(artifact_dir)

    target_ref = canonical_ref(repo_path, manifest.target_ref)
    current_target = rev_parse_optional(repo_path, target_ref)
    if manifest.baseline_commit is not None and current_target != manifest.baseline_commit:
        raise ValueError("local baseline does not match artifact baseline")

    payload_path = payload_path_for_manifest(artifact_dir, manifest)
    if manifest.payload_size > 0:
        import_ref = f"refs/longhaul/imports/{manifest.artifact_id}"
        import_bundle(repo_path, payload_path, manifest.target_ref, import_ref)

    if not object_exists(repo_path, manifest.target_commit, "commit"):
        raise ValueError("target commit is not present after artifact import")

    update_ref(repo_path, target_ref, manifest.target_commit, current_target)
    return manifest


def apply_staged_artifact(repo_path: Path, artifact_id: str, *, expected_repo_id: str, expected_node_id: str) -> ArtifactManifest:
    artifact_dir = artifact_incoming_dir(repo_path, artifact_id)
    manifest = apply_artifact(
        repo_path,
        artifact_dir,
        expected_repo_id=expected_repo_id,
        expected_node_id=expected_node_id,
    )
    state = get_receive_artifact_state(repo_path, artifact_id)
    updated_state = ReceiveArtifactState(
        artifact_id=state.artifact_id,
        sender_node_id=state.sender_node_id,
        receiver_node_id=state.receiver_node_id,
        target_ref=state.target_ref,
        target_commit=state.target_commit,
        segment_count=state.segment_count,
        received_segments=state.received_segments,
        payload_verified=True,
        applied=True,
    )
    upsert_receive_artifact_state(repo_path, updated_state)
    return manifest
