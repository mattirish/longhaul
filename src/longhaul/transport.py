from __future__ import annotations

import shutil
from pathlib import Path

from .messages import MessageEnvelope, read_envelope, write_envelope


def spool_dir(root: Path) -> Path:
    return root


def outgoing_dir(root: Path) -> Path:
    return spool_dir(root) / "outgoing"


def incoming_dir(root: Path) -> Path:
    return spool_dir(root) / "incoming"


def ensure_spool(root: Path) -> None:
    outgoing_dir(root).mkdir(parents=True, exist_ok=True)
    incoming_dir(root).mkdir(parents=True, exist_ok=True)


def export_message(root: Path, envelope: MessageEnvelope) -> Path:
    ensure_spool(root)
    return write_envelope(outgoing_dir(root) / f"{envelope.message_id}-{envelope.message_type}.json", envelope)


def import_message(root: Path, path: Path) -> Path:
    ensure_spool(root)
    destination = incoming_dir(root) / path.name
    shutil.copyfile(path, destination)
    return destination


def list_messages(root: Path, box: str) -> list[Path]:
    base = outgoing_dir(root) if box == "outgoing" else incoming_dir(root)
    if not base.exists():
        return []
    return sorted(item for item in base.iterdir() if item.is_file())


def read_messages(root: Path, box: str) -> list[MessageEnvelope]:
    return [read_envelope(path) for path in list_messages(root, box)]
