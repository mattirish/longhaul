# Protocol

## Purpose

The Longhaul protocol moves a prepared Git-native update payload between endpoints over an extremely constrained, interruption-prone link.

The protocol is designed to:

- minimize interactive exchanges
- support multi-session resume
- verify data incrementally
- avoid mutating repository refs until a complete payload is validated

## Protocol Shape

The protocol is message-oriented and artifact-driven.

The receiver does not negotiate object-by-object during transfer. Instead:

1. the receiver advertises compact repository state
2. the sender prepares an artifact offline
3. the sender transmits artifact segments
4. the receiver records durable progress across sessions
5. the receiver verifies and imports the artifact once complete

## V1 Assumptions

- one sender-receiver pair per sync flow
- one repository per flow
- receiver baseline is known by commit or tracked ref
- target is a normal Git ref
- bidirectional control traffic exists but should be sparse

## Artifact Format

An artifact is a transport container around a Git-native payload.

### Artifact Header

Required fields:

- protocol version
- artifact ID
- repository ID
- sender node ID
- receiver node ID
- baseline commit
- target commit
- payload size
- segment size
- segment count
- whole-artifact hash

### Segment Manifest

Each segment has:

- segment index
- offset
- segment length
- segment hash

The manifest may be transmitted in full or derived from deterministic rules plus a compact digest, depending on transport constraints.

### Payload

The payload is a Git bundle prepared by the sender for the advertised baseline and target ref.

Longhaul does not try to replace Git's own offline packaging here. It adds segmentation, durable receive state, and staged apply behavior around the bundle.

## Message Types

### `OFFER`

Purpose:

- announce a prepared artifact

Fields:

- artifact ID
- repository ID
- baseline commit
- target commit
- payload size
- segment size
- segment count
- whole-artifact hash
- embedded manifest for the file-backed mock transport implementation

### `SEGMENT`

Purpose:

- transmit one verified unit of payload data

Fields:

- artifact ID
- segment index
- segment hash
- payload bytes

In the current implementation, protocol messages are compact Longhaul binary frames rather than JSON development envelopes.

### `NACK_RANGES`

Purpose:

- report which artifact ranges remain missing after one or more sessions

Fields:

- artifact ID
- missing segment ranges
- optional received segment summary

This is an application-layer resume message. It does not replace the transport's own within-session retry logic.

### `COMPLETE`

Purpose:

- announce whole-artifact verification result

Fields:

- artifact ID
- verification status
- whole-artifact hash confirmation

### `APPLY_RESULT`

Purpose:

- report repository import and ref update result

Fields:

- artifact ID
- apply status
- updated ref
- resulting commit hash

## File-Backed Mock Transport

Phase 5 introduces a file-backed transport adapter so protocol behavior can be validated without modem integration.

The file-backed transport model has:

- a spool root
- an `outgoing/` directory for emitted protocol envelopes
- an `incoming/` directory for imported protocol envelopes

Each message is a Longhaul message frame stored in a spool file.

This keeps the transport boundary explicit without depending on the live radio stack.

## FreeDATA Transport Direction

The initial radio-facing adapter targets FreeDATA's socket interface.

The intended boundary is:

- FreeDATA owns live-session reliability, retries, and connection behavior
- Longhaul owns artifact identity, durable receive progress, and staged Git apply

For that reason, the default FreeDATA mode in Longhaul is `data-only`, where Longhaul hands opaque protocol bytes to FreeDATA's data socket without trying to manage the FreeDATA connection state machine itself.

## Resume Semantics

Resume is mandatory in v1.

Rules:

- the receiver persists verified segments immediately
- duplicate valid segments are ignored
- the sender may resume after any interruption
- ref updates are prohibited until the full artifact verifies successfully

Longhaul resume is artifact-level and multi-session.
It is not a replacement for the transport's own packet or burst retry behavior.

## Segment Strategy

Segment sizing should be chosen with transport realities in mind:

- small enough to limit retransmission waste
- large enough to avoid excessive framing overhead
- stable enough to allow deterministic resume bookkeeping

V1 should use fixed-size segments except possibly for the final segment.

## Baseline Strategy

V1 baseline knowledge should be commit- and ref-based, not full object inventory based.

Rationale:

- advertising refs is cheap
- full object inventory exchange can be expensive
- most expected syncs will occur between related histories where a bundle relative to the advertised baseline is enough

If later measurements show that additional inventory exchange saves significant airtime overall, that can be added as an extension.

## Repository Mutation Rules

The receiver must not update refs until:

1. all required segments are present
2. the whole artifact verifies
3. the Git-native payload imports cleanly

If any step fails, the receiver keeps resume state but leaves repository refs unchanged.

## Out Of Scope For V1

- native Git wire protocol compatibility
- arbitrary history reconciliation
- working tree sync semantics
- encryption design
- multi-repository multiplexing
- peer discovery
