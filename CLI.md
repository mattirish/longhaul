# CLI

## Purpose

The v1 CLI should expose the hostile-link replication workflow directly instead of pretending to be a transparent Git remote from day one.

That keeps the first implementation honest about the actual system shape:

- baseline advertisement
- sender-side planning
- artifact creation
- segmented transfer
- receiver-side import

In the current design, the artifact payload is a Git bundle and Longhaul's job is to orchestrate its transfer over a hostile link.

## Principles

- commands should map cleanly to protocol stages
- commands should be scriptable
- commands should work with file-backed mock transport before radio integration
- commands should avoid hidden repository mutation

## Proposed Command Groups

### `longhaul repo`

Repository-local operations.

Initial commands:

- `longhaul repo init`
- `longhaul repo status`
- `longhaul repo advertise`

#### `longhaul repo init`

Purpose:

- initialize Longhaul metadata for an existing Git repository

Expected inputs:

- repository path
- local node ID
- repository ID, if explicitly provided

#### `longhaul repo status`

Purpose:

- show current tracked refs
- show pending artifact state
- show incomplete receive state

#### `longhaul repo advertise`

Purpose:

- emit the compact receiver state needed by a sender to plan an update

Output should include:

- repository ID
- node ID
- tracked refs and commit hashes
- incomplete artifact IDs and missing ranges, if any

### `longhaul plan`

Sender-side planning commands.

Initial commands:

- `longhaul plan artifact`

#### `longhaul plan artifact`

Purpose:

- compute the required Git bundle artifact from a receiver advertisement and a target ref
- write a Longhaul artifact plus manifest

Expected inputs:

- local repository path
- receiver advertisement file
- target ref
- output directory

Expected outputs:

- artifact metadata
- segment manifest
- a segmentable Git bundle payload container

### `longhaul send`

Transport-oriented sender commands.

Initial commands:

- `longhaul send offer`
- `longhaul send segment`

#### `longhaul send offer`

Purpose:

- serialize an artifact offer as a protocol message
- optionally place that message into a file-backed transport spool

#### `longhaul send segment`

Purpose:

- export one artifact segment as a protocol message
- optionally place that message into a file-backed transport spool

Expected inputs:

- artifact directory
- segment index
- output path

### `longhaul transport`

File-backed mock transport commands.

Initial commands:

- `longhaul transport init`
- `longhaul transport status`
- `longhaul transport import`
- `longhaul transport list`
- `longhaul transport read`
- `longhaul transport probe`
- `longhaul transport dispatch`

#### `longhaul transport init`

Purpose:

- initialize a transport root for either the spool transport or the FreeDATA adapter
- persist FreeDATA socket settings for later use

#### `longhaul transport status`

Purpose:

- inspect transport-local state such as spool counts or FreeDATA mirror/config paths

#### `longhaul transport import`

Purpose:

- copy a protocol message into a local spool inbox

#### `longhaul transport list`

Purpose:

- inspect message filenames and message types in a spool inbox or outbox

#### `longhaul transport read`

Purpose:

- inspect full decoded protocol envelopes from a spool inbox or outbox

#### `longhaul transport probe`

Purpose:

- test connectivity to the FreeDATA command socket by issuing a version query

#### `longhaul transport dispatch`

Purpose:

- send a prepared protocol message through either the spool transport or the FreeDATA adapter

For `--transport freedata`, use `--session-mode data-only` for local testmode daemon work when you want to validate data-socket delivery without triggering the FreeDATA connection state machine.
That is also the preferred architectural default: FreeDATA owns live session behavior, while Longhaul stays at the artifact layer.

### `longhaul receive`

Receiver-side transfer commands.

Initial commands:

- `longhaul receive offer`
- `longhaul receive segment`
- `longhaul receive complete`
- `longhaul receive verify`
- `longhaul receive apply`

#### `longhaul receive offer`

Purpose:

- stage an offered artifact for receipt from either a manifest file or an `OFFER` message
- initialize persistent receive state under `.longhaul/`

Expected behavior:

- validate repository and receiver identity
- create durable state for later resume
- report missing ranges immediately

#### `longhaul receive segment`

Purpose:

- accept one segment for a staged artifact from either a raw segment file or a `SEGMENT` message

Expected behavior:

- verify length and segment hash before persistence
- store the segment durably
- update artifact-level missing-range state without trying to replace transport-level retry behavior

#### `longhaul receive complete`

Purpose:

- assemble a staged payload from received segments
- verify the assembled payload against the manifest

Expected behavior:

- reject incomplete artifacts
- verify per-segment integrity again during assembly
- mark the payload as verified only after whole-payload validation passes
- optionally emit a `COMPLETE` message into the local spool outbox

#### `longhaul receive verify`

Purpose:

- verify a fully assembled artifact directory against its manifest

Expected behavior:

- verify payload size and whole-payload hash
- recompute segment hashes
- reject artifacts whose manifest and payload do not match

#### `longhaul receive apply`

Purpose:

- import a fully verified artifact into the local Git repository
- update the target ref only after successful import
- reject apply when the local baseline does not match the artifact baseline
- optionally emit an `APPLY_RESULT` message into the local spool outbox

#### `longhaul receive nack`

Purpose:

- emit a compact `NACK_RANGES` message for a staged incomplete artifact when the sender needs explicit multi-session resume guidance

## Suggested V1 Workflow

1. receiver runs `longhaul repo advertise`
2. sender runs `longhaul plan artifact`
3. sender runs `longhaul send offer` and places the message in a transport spool
4. receiver imports the `OFFER` message and runs `longhaul receive offer`
5. sender emits `SEGMENT` messages through the transport spool
6. receiver imports and processes segments with `longhaul receive segment`
7. receiver emits `NACK_RANGES` only if explicit artifact-level resume guidance is needed
8. sender retransmits only missing ranges
9. receiver runs `longhaul receive complete`
10. receiver runs `longhaul receive apply`

## Deferred UX

The CLI should not hide the artifact and resume model in v1.

Future versions may add:

- a higher-level sync command
- daemonized folder watching
- transport-specific adapters
- a user-facing inbox/outbox abstraction

Those should be layered on top of the explicit commands above, not used to define the core behavior.
