from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from .freedata import FreeDataCommandClient, FreeDataDataClient, FreeDataSession, FreeDataSocketConfig
from .messages import MessageEnvelope, message_filename, read_envelope, serialize_envelope, write_envelope


@dataclass
class TransportMessage:
    path: str
    message_id: str
    message_type: str


class TransportAdapter(Protocol):
    """Transport adapters move opaque Longhaul messages between inboxes and outboxes."""

    def send(self, envelope: MessageEnvelope) -> Path:
        ...

    def ingest(self, path: Path) -> Path:
        ...

    def list(self, box: str) -> list[Path]:
        ...

    def read(self, box: str) -> list[MessageEnvelope]:
        ...


@dataclass
class SpoolAdapter:
    root: Path

    @property
    def outgoing_dir(self) -> Path:
        return self.root / "outgoing"

    @property
    def incoming_dir(self) -> Path:
        return self.root / "incoming"

    def ensure(self) -> None:
        self.outgoing_dir.mkdir(parents=True, exist_ok=True)
        self.incoming_dir.mkdir(parents=True, exist_ok=True)

    def send(self, envelope: MessageEnvelope) -> Path:
        self.ensure()
        return write_envelope(
            self.outgoing_dir / message_filename(envelope),
            envelope,
        )

    def ingest(self, path: Path) -> Path:
        self.ensure()
        envelope = read_envelope(path)
        return write_envelope(
            self.incoming_dir / message_filename(envelope),
            envelope,
        )

    def list(self, box: str) -> list[Path]:
        self.ensure()
        base = self.outgoing_dir if box == "outgoing" else self.incoming_dir
        return sorted(item for item in base.iterdir() if item.is_file())

    def read(self, box: str) -> list[MessageEnvelope]:
        return [read_envelope(path) for path in self.list(box)]


@dataclass
class FreeDataAdapter:
    """
    FreeDATA transport adapter backed by the daemon command/data socket interface.

    The adapter mirrors emitted messages locally for inspection and replay, and then attempts
    to hand the same envelope bytes to a reachable FreeDATA daemon.
    """

    root: Path
    station_id: str
    peer_id: str
    api_url: str | None = None
    host: str = "127.0.0.1"
    cmd_port: int = 9000
    data_port: int = 9001
    bandwidth: int = 2300
    session_mode: str = "auto"

    CONFIG_FILE = "freedata-config.json"

    @property
    def mirror(self) -> SpoolAdapter:
        return SpoolAdapter(self.root / "mirror")

    @property
    def config_path(self) -> Path:
        return self.root / self.CONFIG_FILE

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.mirror.ensure()
        self.config_path.write_text(
            json.dumps(
                {
                    "transport": "freedata",
                    "station_id": self.station_id,
                    "peer_id": self.peer_id,
                    "api_url": self.api_url,
                    "host": self.host,
                    "cmd_port": self.cmd_port,
                    "data_port": self.data_port,
                    "bandwidth": self.bandwidth,
                    "session_mode": self.session_mode,
                },
                indent=2,
            )
            + "\n"
        )

    @property
    def socket_config(self) -> FreeDataSocketConfig:
        return FreeDataSocketConfig(
            host=self.host,
            cmd_port=self.cmd_port,
            data_port=self.data_port,
            mycall=self.station_id,
            peer_call=self.peer_id,
            bandwidth=self.bandwidth,
            session_mode=self.session_mode,
        )

    def send(self, envelope: MessageEnvelope) -> Path:
        self.ensure()
        path = write_envelope(
            self.mirror.outgoing_dir / message_filename(envelope),
            envelope,
        )
        payload = serialize_envelope(envelope)
        data_client = FreeDataDataClient(self.socket_config)
        if self.session_mode == "data-only":
            data_client.send(payload)
            return path

        command_client = FreeDataCommandClient(self.socket_config)
        version = command_client.version()
        if not any("VERSION FREEDATA" in line for line in version):
            raise RuntimeError("FreeDATA daemon did not report VERSION FREEDATA")
        with FreeDataSession(self.socket_config) as session:
            session.connect()
            data_client.send(payload)
            session.disconnect()
        return path

    def ingest(self, path: Path) -> Path:
        self.ensure()
        envelope = read_envelope(path)
        return write_envelope(
            self.mirror.incoming_dir / message_filename(envelope),
            envelope,
        )

    def list(self, box: str) -> list[Path]:
        self.ensure()
        return self.mirror.list(box)

    def read(self, box: str) -> list[MessageEnvelope]:
        self.ensure()
        return self.mirror.read(box)


def spool_adapter(root: Path) -> SpoolAdapter:
    return SpoolAdapter(root)


def freedata_adapter(
    root: Path,
    *,
    station_id: str,
    peer_id: str,
    api_url: str | None = None,
    host: str = "127.0.0.1",
    cmd_port: int = 9000,
    data_port: int = 9001,
    bandwidth: int = 2300,
    session_mode: str = "auto",
) -> FreeDataAdapter:
    return FreeDataAdapter(
        root=root,
        station_id=station_id,
        peer_id=peer_id,
        api_url=api_url,
        host=host,
        cmd_port=cmd_port,
        data_port=data_port,
        bandwidth=bandwidth,
        session_mode=session_mode,
    )


def export_message(root: Path, envelope: MessageEnvelope) -> Path:
    return spool_adapter(root).send(envelope)


def import_message(root: Path, path: Path) -> Path:
    return spool_adapter(root).ingest(path)


def list_messages(root: Path, box: str) -> list[Path]:
    return spool_adapter(root).list(box)


def read_messages(root: Path, box: str) -> list[MessageEnvelope]:
    return spool_adapter(root).read(box)


def summarize_messages(paths: list[Path]) -> list[TransportMessage]:
    summary: list[TransportMessage] = []
    for path in paths:
        envelope = read_envelope(path)
        summary.append(
            TransportMessage(
                path=str(path),
                message_id=envelope.message_id,
                message_type=envelope.message_type,
            )
        )
    return summary


def serialize_transport_messages(messages: list[TransportMessage]) -> list[dict]:
    return [asdict(message) for message in messages]
