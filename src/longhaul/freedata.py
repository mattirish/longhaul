from __future__ import annotations

import socket
from dataclasses import dataclass


@dataclass
class FreeDataSocketConfig:
    host: str = "127.0.0.1"
    cmd_port: int = 9000
    data_port: int = 9001
    mycall: str = "N0CALL"
    peer_call: str = "N0CALL"
    bandwidth: int = 2300
    command_timeout_s: float = 5.0
    data_timeout_s: float = 10.0


def _recv_until_timeout(sock: socket.socket, timeout_s: float) -> list[str]:
    sock.settimeout(timeout_s)
    chunks: list[str] = []
    while True:
        try:
            data = sock.recv(4096)
        except socket.timeout:
            break
        if not data:
            break
        chunks.append(data.decode(errors="replace"))
        if chunks and chunks[-1].endswith("\r"):
            break
    return [line.strip() for line in "".join(chunks).split("\r") if line.strip()]


class FreeDataCommandClient:
    def __init__(self, config: FreeDataSocketConfig):
        self.config = config

    def transact(self, *commands: str) -> list[str]:
        with socket.create_connection(
            (self.config.host, self.config.cmd_port),
            timeout=self.config.command_timeout_s,
        ) as sock:
            for command in commands:
                sock.sendall(f"{command}\r".encode())
            return _recv_until_timeout(sock, self.config.command_timeout_s)

    def version(self) -> list[str]:
        return self.transact("VERSION")

    def connect(self) -> list[str]:
        return self.transact(
            f"MYCALL {self.config.mycall}",
            f"BW {self.config.bandwidth}",
            f"CONNECT {self.config.mycall} {self.config.peer_call}",
        )

    def disconnect(self) -> list[str]:
        return self.transact("DISCONNECT")


class FreeDataDataClient:
    def __init__(self, config: FreeDataSocketConfig):
        self.config = config

    def send(self, payload: bytes) -> None:
        with socket.create_connection(
            (self.config.host, self.config.data_port),
            timeout=self.config.data_timeout_s,
        ) as sock:
            sock.sendall(payload)
