# FreeDATA Integration

## Current State

Longhaul now has a concrete FreeDATA transport adapter and the official FreeDATA source is vendored as a submodule under [vendor/FreeDATA](/Users/mattirish_1/projects/ham/rfsync/vendor/FreeDATA).

The current integration target is FreeDATA's socket interface:

- command socket
- data socket

Longhaul uses the command socket for:

- `VERSION`
- `MYCALL`
- `BW`
- `CONNECT`
- `DISCONNECT`

Longhaul uses the data socket for:

- opaque Longhaul message envelope bytes

Longhaul now supports two FreeDATA session modes:

- `auto`: issue `VERSION`, `MYCALL`, `BW`, `CONNECT`, send data, then `DISCONNECT`
- `data-only`: send envelope bytes directly to the FreeDATA data socket without invoking the connection state machine

## What Was Validated

The following was validated locally in this repository:

- the bundled FreeDATA `libcodec2` loads correctly when the daemon is run as `x86_64` under Rosetta on Apple Silicon
- the FreeDATA socket interface can be started with a local config
- `longhaul transport probe --transport freedata ...` successfully reaches the real command socket and receives `VERSION FREEDATA`
- `longhaul transport dispatch --transport freedata ...` successfully sends a Longhaul envelope through the real FreeDATA command/data socket path
- FreeDATA logs show the exact Longhaul JSON envelope arriving on the data socket
- in FreeDATA test mode, the data socket now writes one complete payload per connection into a local loopback inbox
- `longhaul transport loopback-import ...` can ingest those loopback payloads into a Longhaul spool as normal `OFFER` and `SEGMENT` envelopes
- a full local multi-segment loop now works end-to-end: sender plans an artifact, dispatches `OFFER` plus `SEGMENT` messages through the live FreeDATA daemon in `data-only` mode, receiver stages and assembles the artifact, verifies it, and advances to the target commit

## Current Blocker

The current local daemon bootstrap uses an intentionally invalid callsign so modem startup short-circuits while the socket interface still starts.

That is enough for:

- command socket probe
- socket interface validation
- data socket payload delivery

It is not enough for:

- a real FreeDATA P2P session
- modem-backed payload transfer

That original blocker has now been reduced.

Longhaul patches the vendored FreeDATA submodule to expose `EXP.enable_testmode` as a real runtime option. In that mode:

- FreeDATA starts `rf_modem` without initializing live audio hardware
- the socket interface starts normally
- the earlier `ctx.rf_modem is None` crash in the `CONNECT` path is avoided

The remaining limitation is narrower:

- a socket-interface `CONNECT` in test mode still does not complete a real modem-backed peer session
- asynchronous `CONNECT` / `DISCONNECT` responses can race with the short-lived Longhaul command client
- the daemon remains up, but a full peer session is still not established in this local no-RF mode

For local development, `data-only` is currently the recommended mode because it validates Longhaul envelope delivery into the live FreeDATA daemon without dragging in the unstable local peer-session path.

## Apple Silicon Note

On this machine, the bundled FreeDATA macOS `libcodec2` is `x86_64`.

That means:

- native `arm64` Python cannot load it
- the FreeDATA daemon must currently run under Rosetta with an `x86_64` Python environment

The working local daemon command used during validation was:

```bash
FREEDATA_CONFIG=/tmp/longhaul-freedata-live.ini arch -x86_64 .venv-x86/bin/python vendor/FreeDATA/freedata_server/server.py
```

## Local Validation Flow

For a full end-to-end local loop, use [scripts/run-freedata-loopback.sh](/Users/mattirish_1/projects/ham/rfsync/scripts/run-freedata-loopback.sh). It:

- starts the patched local FreeDATA daemon in test mode
- provisions throwaway sender and receiver Git repos
- plans a multi-segment artifact
- dispatches `OFFER` and all `SEGMENT` messages through the live FreeDATA data socket
- imports looped-back payloads into a receiver spool
- stages, verifies, and applies the artifact on the receiver
- prints a JSON summary with the final receiver head

Example:

```bash
scripts/run-freedata-loopback.sh
```

1. Initialize a FreeDATA transport root:

```bash
PYTHONPATH=src python3 -m longhaul.cli transport init \
  --transport freedata \
  --root /tmp/longhaul-freedata \
  --station-id N0CALL \
  --peer-id K0PEER \
  --host 127.0.0.1 \
  --cmd-port 9100 \
  --data-port 9101
```

2. Probe the command socket:

```bash
PYTHONPATH=src python3 -m longhaul.cli transport probe \
  --transport freedata \
  --root /tmp/longhaul-freedata \
  --station-id N0CALL \
  --peer-id K0PEER \
  --host 127.0.0.1 \
  --cmd-port 9100 \
  --data-port 9101
```

3. Dispatch a prepared message:

```bash
PYTHONPATH=src python3 -m longhaul.cli transport dispatch \
  --transport freedata \
  --root /tmp/longhaul-freedata \
  --message /tmp/longhaul-freedata-offer.json \
  --station-id N0CALL \
  --peer-id K0PEER \
  --host 127.0.0.1 \
  --cmd-port 9100 \
  --data-port 9101 \
  --session-mode data-only
```

4. Import the looped-back payload into a receiver spool:

```bash
PYTHONPATH=src python3 -m longhaul.cli transport loopback-import \
  --inbox /tmp/freedata_socket_inbox \
  --spool /tmp/longhaul-receiver-spool
```

## Next Work

The next meaningful integration steps are:

- determine whether FreeDATA test mode can be extended to simulate a full peer session instead of only looping back the data socket payload
- formalize the local loop harness into a repeatable integration test script
- validate Longhaul transfer over a real modem-backed FreeDATA session once the daemon bootstrap is stable
