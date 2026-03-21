from __future__ import annotations

import json
import os
import subprocess
import unittest
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

from longhaul.messages import MESSAGE_EXTENSION, new_envelope, read_envelope, write_envelope
from longhaul.transport import import_message, spool_adapter


class SpoolAdapterTest(unittest.TestCase):
    def test_import_message_normalizes_incoming_filename(self) -> None:
        with TemporaryDirectory() as tmp:
            spool_root = Path(tmp) / "spool"
            source_dir = Path(tmp) / "source"
            envelope = new_envelope("OFFER", {"artifact_id": "artifact-1"})
            source_path = write_envelope(source_dir / "random-name.json", envelope)

            destination = import_message(spool_root, source_path)

            self.assertEqual(
                destination.name,
                f"{envelope.message_id}-{envelope.message_type}{MESSAGE_EXTENSION}",
            )
            self.assertTrue(destination.exists())
            self.assertEqual(read_envelope(destination).message_type, "OFFER")

    def test_loopback_imported_messages_land_in_incoming_box(self) -> None:
        with TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "freedata_socket_inbox"
            spool_root = Path(tmp) / "spool"
            inbox.mkdir(parents=True, exist_ok=True)
            envelope = new_envelope(
                "SEGMENT",
                {
                    "artifact_id": str(uuid.uuid4()),
                    "index": 0,
                    "sha256": "00" * 32,
                    "data": "",
                },
            )
            write_envelope(inbox / "freedata-raw.json", envelope)

            subprocess.run(
                [
                    "python3",
                    "-m",
                    "longhaul.cli",
                    "transport",
                    "loopback-import",
                    "--inbox",
                    str(inbox),
                    "--spool",
                    str(spool_root),
                ],
                check=True,
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "PYTHONPATH": "src"},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            adapter = spool_adapter(spool_root)
            incoming = adapter.list("incoming")
            outgoing = adapter.list("outgoing")
            self.assertEqual(len(incoming), 1)
            self.assertEqual(len(outgoing), 0)
            self.assertEqual(incoming[0].name, f"{envelope.message_id}-{envelope.message_type}{MESSAGE_EXTENSION}")
            self.assertEqual(read_envelope(incoming[0]).payload["index"], 0)


if __name__ == "__main__":
    unittest.main()
