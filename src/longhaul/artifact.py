from __future__ import annotations

import hashlib
import json
import math
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from .git import object_closure, pack_objects, rev_parse


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
        target_ref=target_ref,
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
