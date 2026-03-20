# Implementation Plan

## Objective

Build the minimum viable Longhaul engine that can move a normal Git repository from a known baseline to a target ref over a hostile link with resumable segmented transfer.

## Guiding Rule

Do not integrate radio transport before proving the artifact, resume, and import model locally.

The highest technical risk is in update planning and resumable transfer semantics, not in wiring bytes into a modem.

## Phase 1: Repository Metadata And State Advertisement

Deliverables:

- local Longhaul metadata for a Git repository
- stable repository ID and node ID handling
- advertisement generation from current refs and in-progress receive state

Acceptance criteria:

- a repository can emit a compact state advertisement
- advertisement contents are deterministic
- advertisement is sufficient for sender-side planning

## Phase 2: Artifact Planning

Deliverables:

- target ref selection
- baseline-to-target object closure computation
- artifact metadata file
- segment manifest generation

Acceptance criteria:

- given a receiver baseline and target ref, the sender can create a portable artifact description
- resulting payload includes only required Git-native objects for the chosen update path

## Phase 3: Artifact Import

Deliverables:

- staged artifact verification
- Git-native payload import into a local repository
- transactional ref update after successful import

Acceptance criteria:

- import does not mutate refs when verification fails
- successful import moves the selected ref to the target commit

## Phase 4: Segmented Transfer And Resume

Deliverables:

- fixed-size segment generation
- per-segment hash verification
- persistent receive state
- missing-range reporting
- duplicate segment handling

Acceptance criteria:

- interrupted transfer can resume without replaying verified segments
- receiver can identify exactly which segments remain missing
- retransmission is limited to missing ranges

## Phase 5: File-Backed Mock Transport

Deliverables:

- protocol message serialization
- local export/import transport adapter
- test harness for multi-session transfer

Acceptance criteria:

- complete end-to-end update using only local files as transport
- protocol messages remain transport-neutral

## Phase 6: Radio Transport Adapter

Deliverables:

- transport adapter abstraction
- first concrete adapter for the initial radio stack
- operational settings for segment sizing and pacing

Acceptance criteria:

- same artifact and protocol implementation works over the real transport
- radio integration does not change repository or artifact semantics

## Data Model Sketch

Repository-local metadata:

- `repo_id`
- `node_id`
- tracked refs

Receive-state metadata:

- `artifact_id`
- expected target commit
- segment count
- received ranges
- per-segment verification state
- whole-artifact verification state

Artifact metadata:

- sender/receiver IDs
- baseline commit
- target commit
- payload size
- segment size
- segment hashes
- whole-artifact hash

## Testing Strategy

Prioritize deterministic local tests.

Required test layers:

- unit tests for manifest and range logic
- repository fixture tests for baseline-to-target planning
- interrupted-transfer tests for resume behavior
- corruption tests for per-segment and whole-artifact verification
- import tests that verify refs remain unchanged on failure

## Open Questions

- should the payload be a raw packfile or a more structured bundle-derived container
- what segment size best balances framing overhead versus retransmission waste
- how compact should resume state encoding be on the wire
- whether ref advertisements alone are sufficient for expected real-world histories in v1

These are implementation questions, not architectural blockers. The current design already constrains them to the right solution space.
