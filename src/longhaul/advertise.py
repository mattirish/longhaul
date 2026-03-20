from __future__ import annotations

from pathlib import Path

from .artifact import missing_ranges
from .git import current_head, refs
from .metadata import load_receive_artifact_states, load_repo_config


def incomplete_artifacts(repo_path: Path) -> list[dict]:
    artifacts: list[dict] = []
    for state in load_receive_artifact_states(repo_path):
        if state.applied:
            continue
        artifacts.append(
            {
                "artifact_id": state.artifact_id,
                "target_ref": state.target_ref,
                "target_commit": state.target_commit,
                "received_segments": state.received_segments,
                "missing_ranges": missing_ranges(state.segment_count, state.received_segments),
                "payload_verified": state.payload_verified,
            }
        )
    return artifacts


def build_advertisement(repo_path: Path) -> dict:
    config = load_repo_config(repo_path)
    return {
        "protocol_version": 1,
        "repo_id": config.repo_id,
        "node_id": config.node_id,
        "head": current_head(repo_path),
        "refs": refs(repo_path),
        "incomplete_artifacts": incomplete_artifacts(repo_path),
    }
