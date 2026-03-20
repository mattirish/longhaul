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


def longhaul_dir(repo_path: Path) -> Path:
    return repo_path / LONGHAUL_DIR


def config_path(repo_path: Path) -> Path:
    return longhaul_dir(repo_path) / CONFIG_FILE


def receive_state_path(repo_path: Path) -> Path:
    return longhaul_dir(repo_path) / RECEIVE_STATE_FILE


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
