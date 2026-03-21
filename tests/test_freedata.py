from __future__ import annotations

import json
import socketserver
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from longhaul.freedata import FreeDataCommandClient, FreeDataSession, FreeDataSocketConfig
from longhaul.messages import deserialize_envelope, new_envelope
from longhaul.transport import freedata_adapter


class _CommandHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        self.server.command_log = []  # type: ignore[attr-defined]
        buffer = ""
        while True:
            data = self.request.recv(4096)
            if not data:
                break
            buffer += data.decode()
            while "\r" in buffer:
                line, buffer = buffer.split("\r", 1)
                if not line:
                    continue
                self.server.command_log.append(line)  # type: ignore[attr-defined]
                if line == "VERSION":
                    self.request.sendall(b"VERSION FREEDATA\r")
                elif line.startswith("MYCALL "):
                    self.request.sendall(b"OK\rUNENCRYPTED LINK\rENCRYPTION DISABLED\r")
                elif line.startswith("BW "):
                    self.request.sendall(b"OK\r")
                elif line.startswith("CONNECT "):
                    self.request.sendall(b"OK\rREGISTERED N0CALL\rUNENCRYPTED LINK\r")
                elif line == "DISCONNECT":
                    self.request.sendall(b"OK\rDISCONNECTED\r")
                else:
                    self.request.sendall(b"WRONG\r")


class _DataHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        self.server.payloads.append(self.request.recv(65535))  # type: ignore[attr-defined]


class _ThreadedServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True


class FreeDataIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.command_server = _ThreadedServer(("127.0.0.1", 0), _CommandHandler)
        self.command_server.command_log = []  # type: ignore[attr-defined]
        self.data_server = _ThreadedServer(("127.0.0.1", 0), _DataHandler)
        self.data_server.payloads = []  # type: ignore[attr-defined]
        self.command_thread = threading.Thread(target=self.command_server.serve_forever, daemon=True)
        self.data_thread = threading.Thread(target=self.data_server.serve_forever, daemon=True)
        self.command_thread.start()
        self.data_thread.start()
        self.config = FreeDataSocketConfig(
            host="127.0.0.1",
            cmd_port=self.command_server.server_address[1],
            data_port=self.data_server.server_address[1],
            mycall="N0CALL",
            peer_call="K0PEER",
            bandwidth=2300,
            command_timeout_s=0.2,
            data_timeout_s=0.2,
        )

    def tearDown(self) -> None:
        self.command_server.shutdown()
        self.data_server.shutdown()
        self.command_server.server_close()
        self.data_server.server_close()
        self.command_thread.join(timeout=1)
        self.data_thread.join(timeout=1)

    def test_version_probe(self) -> None:
        responses = FreeDataCommandClient(self.config).version()
        self.assertIn("VERSION FREEDATA", responses)

    def test_session_connect_disconnect_uses_same_socket(self) -> None:
        with FreeDataSession(self.config) as session:
            responses = session.connect()
            self.assertTrue(any("REGISTERED" in line for line in responses))
            disconnect = session.disconnect()
            self.assertIn("DISCONNECTED", disconnect)

    def test_adapter_sends_envelope_and_mirrors_locally(self) -> None:
        with TemporaryDirectory() as tmp:
            adapter = freedata_adapter(
                Path(tmp),
                station_id=self.config.mycall,
                peer_id=self.config.peer_call,
                host=self.config.host,
                cmd_port=self.config.cmd_port,
                data_port=self.config.data_port,
                bandwidth=self.config.bandwidth,
            )
            envelope = new_envelope("TEST", {"hello": "world"})
            mirror_path = adapter.send(envelope)
            self.assertTrue(mirror_path.exists())
            self.assertTrue(self.data_server.payloads)  # type: ignore[attr-defined]
            payload = deserialize_envelope(self.data_server.payloads[0])  # type: ignore[index]
            self.assertEqual(payload.message_id, envelope.message_id)
            self.assertEqual(payload.message_type, "TEST")


if __name__ == "__main__":
    unittest.main()
