from __future__ import annotations

from pathlib import Path

from .git import current_head, refs
from .metadata import load_receive_state, load_repo_config


def build_advertisement(repo_path: Path) -> dict:
    config = load_repo_config(repo_path)
    return {
        "protocol_version": 1,
        "repo_id": config.repo_id,
        "node_id": config.node_id,
        "head": current_head(repo_path),
        "refs": refs(repo_path),
        "incomplete_artifacts": load_receive_state(repo_path),
    }
