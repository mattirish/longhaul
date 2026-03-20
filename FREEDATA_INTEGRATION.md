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

## What Was Validated

The following was validated locally in this repository:

- the bundled FreeDATA `libcodec2` loads correctly when the daemon is run as `x86_64` under Rosetta on Apple Silicon
- the FreeDATA socket interface can be started with a local config
- `longhaul transport probe --transport freedata ...` successfully reaches the real command socket and receives `VERSION FREEDATA`
- `longhaul transport dispatch --transport freedata ...` successfully sends a Longhaul envelope through the real FreeDATA command/data socket path
- FreeDATA logs show the exact Longhaul JSON envelope arriving on the data socket

## Current Blocker

The current local daemon bootstrap uses an intentionally invalid callsign so modem startup short-circuits while the socket interface still starts.

That is enough for:

- command socket probe
- socket interface validation
- data socket payload delivery

It is not enough for:

- a real FreeDATA P2P session
- modem-backed payload transfer

Observed behavior:

- `CONNECT` creates a `P2PConnection`
- FreeDATA then attempts to transmit through `ctx.rf_modem`
- because the modem did not start, `ctx.rf_modem` is `None`
- the daemon throws an exception in the connection flow

This is a FreeDATA runtime/bootstrap issue for local development, not a Longhaul envelope-format issue.

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
  --data-port 9101
```

## Next Work

The next meaningful integration steps are:

- create a repeatable local FreeDATA config or startup path that keeps the socket interface up without crashing the connection flow
- determine whether FreeDATA has a supported test mode or dummy modem path that still permits `CONNECT` and payload movement
- validate Longhaul transfer over a real modem-backed FreeDATA session once the daemon bootstrap is stable
