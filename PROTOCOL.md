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
4. the receiver reports only compact receipt state or missing ranges
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

The payload is a Git-native object payload prepared by the sender. In v1 this should be a packfile or packfile-equivalent container containing exactly the required objects for the target closure relative to the advertised baseline.

## Message Types

### `HELLO`

Purpose:

- establish protocol version
- identify peer
- identify repository context

Fields:

- protocol version
- node ID
- repository ID

### `STATE`

Purpose:

- advertise receiver baseline
- advertise incomplete transfer state

Fields:

- node ID
- repository ID
- tracked refs and commit hashes
- current baseline commit for requested ref
- incomplete artifact IDs, if any
- received segment ranges or bitmap summary, if resuming

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

In the file-backed mock transport, the payload bytes are serialized inside a JSON envelope using a transport-safe encoding.

### `NACK_RANGES`

Purpose:

- request retransmission of missing ranges only

Fields:

- artifact ID
- missing segment ranges
- optional received segment summary

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

Each message is a JSON envelope containing:

- message ID
- message type
- protocol version
- payload

This is not the final on-air framing. It is a development transport that forces the protocol boundary to remain explicit while keeping message contents inspectable during implementation.

## Resume Semantics

Resume is mandatory in v1.

Rules:

- the receiver persists verified segments immediately
- duplicate valid segments are ignored
- the sender may resume after any interruption
- the receiver reports compact missing ranges instead of per-segment acknowledgements
- ref updates are prohibited until the full artifact verifies successfully

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
- most expected syncs will occur between related histories where commit ancestry is enough to compute a useful minimal payload

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
