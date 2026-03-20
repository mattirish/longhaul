from __future__ import annotations

import hashlib
import json
import math
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from .git import canonical_ref, object_closure, object_exists, pack_objects, rev_parse, rev_parse_optional, unpack_objects, update_ref


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
    payload_path = artifact_dir / "payload.pack"
    pack_objects(repo_path, object_ids, payload_path)

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
        unpack_objects(repo_path, payload_path)

    if not object_exists(repo_path, manifest.target_commit, "commit"):
        raise ValueError("target commit is not present after artifact import")

    update_ref(repo_path, target_ref, manifest.target_commit, current_target)
    return manifest
