from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path


LONGHAUL_DIR = ".longhaul"
CONFIG_FILE = "config.json"
RECEIVE_STATE_FILE = "receive-state.json"


@dataclass
class RepoConfig:
    repo_id: str
    node_id: str


@dataclass
class ReceiveArtifactState:
    artifact_id: str
    sender_node_id: str
    receiver_node_id: str
    target_ref: str
    target_commit: str
    segment_count: int
    received_segments: list[int]
    payload_verified: bool
    applied: bool


def longhaul_dir(repo_path: Path) -> Path:
    return repo_path / LONGHAUL_DIR


def config_path(repo_path: Path) -> Path:
    return longhaul_dir(repo_path) / CONFIG_FILE


def receive_state_path(repo_path: Path) -> Path:
    return longhaul_dir(repo_path) / RECEIVE_STATE_FILE


def incoming_dir(repo_path: Path) -> Path:
    return longhaul_dir(repo_path) / "incoming"


def artifact_incoming_dir(repo_path: Path, artifact_id: str) -> Path:
    return incoming_dir(repo_path) / artifact_id


def artifact_segment_dir(repo_path: Path, artifact_id: str) -> Path:
    return artifact_incoming_dir(repo_path, artifact_id) / "segments"


def init_repo_config(
    repo_path: Path,
    node_id: str,
    repo_id: str | None = None,
    *,
    force: bool = False,
) -> RepoConfig:
    if config_path(repo_path).exists() and not force:
        raise FileExistsError(f"Longhaul repo metadata already exists in {repo_path}")
    config = RepoConfig(repo_id=repo_id or str(uuid.uuid4()), node_id=node_id)
    base = longhaul_dir(repo_path)
    base.mkdir(exist_ok=True)
    config_path(repo_path).write_text(json.dumps(asdict(config), indent=2) + "\n")
    if not receive_state_path(repo_path).exists():
        receive_state_path(repo_path).write_text("[]\n")
    incoming_dir(repo_path).mkdir(exist_ok=True)
    return config


def load_repo_config(repo_path: Path) -> RepoConfig:
    path = config_path(repo_path)
    if not path.exists():
        raise FileNotFoundError(f"Longhaul repo metadata not initialized in {repo_path}")
    data = json.loads(path.read_text())
    return RepoConfig(**data)


def load_receive_state(repo_path: Path) -> list[dict]:
    path = receive_state_path(repo_path)
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError("receive-state.json must contain a list")
    return data


def load_receive_artifact_states(repo_path: Path) -> list[ReceiveArtifactState]:
    return [ReceiveArtifactState(**item) for item in load_receive_state(repo_path)]


def save_receive_artifact_states(repo_path: Path, states: list[ReceiveArtifactState]) -> None:
    receive_state_path(repo_path).write_text(
        json.dumps([asdict(state) for state in states], indent=2) + "\n"
    )


def get_receive_artifact_state(repo_path: Path, artifact_id: str) -> ReceiveArtifactState:
    for state in load_receive_artifact_states(repo_path):
        if state.artifact_id == artifact_id:
            return state
    raise FileNotFoundError(f"no receive state for artifact {artifact_id}")


def upsert_receive_artifact_state(repo_path: Path, new_state: ReceiveArtifactState) -> ReceiveArtifactState:
    states = load_receive_artifact_states(repo_path)
    replaced = False
    for index, state in enumerate(states):
        if state.artifact_id == new_state.artifact_id:
            states[index] = new_state
            replaced = True
            break
    if not replaced:
        states.append(new_state)
    save_receive_artifact_states(repo_path, states)
    return new_state
