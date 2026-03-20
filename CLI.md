# CLI

## Purpose

The v1 CLI should expose the hostile-link replication workflow directly instead of pretending to be a transparent Git remote from day one.

That keeps the first implementation honest about the actual system shape:

- baseline advertisement
- sender-side planning
- artifact creation
- segmented transfer
- receiver-side import

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

- compute the required Git-native payload from a receiver advertisement and a target ref
- write a Longhaul artifact plus manifest

Expected inputs:

- local repository path
- receiver advertisement file
- target ref
- output directory

Expected outputs:

- artifact metadata
- segment manifest
- payload segments or a segmentable payload container

### `longhaul send`

Transport-oriented sender commands.

Initial commands:

- `longhaul send offer`
- `longhaul send segments`

#### `longhaul send offer`

Purpose:

- emit an `OFFER` message for an artifact

#### `longhaul send segments`

Purpose:

- emit requested or all artifact segments for a given artifact

Expected inputs:

- artifact directory
- optional requested segment ranges

### `longhaul receive`

Receiver-side transfer commands.

Initial commands:

- `longhaul receive offer`
- `longhaul receive verify`
- `longhaul receive apply`

#### `longhaul receive verify`

Purpose:

- verify an artifact on disk against its manifest

Expected behavior:

- verify payload size and whole-payload hash
- recompute segment hashes
- reject artifacts whose manifest and payload do not match

#### `longhaul receive apply`

Purpose:

- import a fully verified artifact into the local Git repository
- update the target ref only after successful import
- reject apply when the local baseline does not match the artifact baseline

### `longhaul transport`

Transport adapter commands for early testing.

Initial commands:

- `longhaul transport export`
- `longhaul transport import`

These commands support a file-based mock transport first so the protocol and artifact design can be tested without requiring radio integration.

## Suggested V1 Workflow

1. receiver runs `longhaul repo advertise`
2. sender runs `longhaul plan artifact`
3. sender emits an offer and segments through a transport adapter
4. receiver stages and stores verified segments
5. receiver reports missing ranges
6. sender retransmits only missing ranges
7. receiver runs `longhaul receive apply`

## Deferred UX

The CLI should not hide the artifact and resume model in v1.

Future versions may add:

- a higher-level sync command
- daemonized folder watching
- transport-specific adapters
- a user-facing inbox/outbox abstraction

Those should be layered on top of the explicit commands above, not used to define the core behavior.
