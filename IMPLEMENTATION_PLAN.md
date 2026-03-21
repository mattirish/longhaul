# Implementation Plan

## Objective

Build the minimum viable Longhaul engine that can move a normal Git repository from a known baseline to a target ref over a hostile link by segmenting and resuming a Git bundle artifact.

## Guiding Rule

Do not integrate radio transport before proving the artifact, resume, and import model locally.

The highest technical risk is in multi-session resume and apply semantics, not in inventing a new payload format or wiring bytes into a modem.

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
- bundle artifact generation from advertised baseline to target ref
- artifact metadata file
- segment manifest generation

Acceptance criteria:

- given a receiver baseline and target ref, the sender can create a portable Git bundle artifact description
- resulting payload is Git-native and efficient enough to benchmark directly against `git bundle`

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
- staged payload assembly before apply

Acceptance criteria:

- interrupted transfer can resume without replaying verified segments
- receiver can identify exactly which segments remain missing
- retransmission is limited to missing ranges
- repository refs remain unchanged until staged payload assembly and verification succeed

## Phase 5: File-Backed Mock Transport

Deliverables:

- protocol message serialization
- local export/import transport adapter
- test harness for multi-session transfer
- spool inbox/outbox inspection tools

Acceptance criteria:

- complete end-to-end update using only local files as transport
- protocol messages remain transport-neutral
- sender and receiver can exchange `OFFER`, `SEGMENT`, and optional resume/result messages through the spool model

## Phase 6: Radio Transport Adapter

Deliverables:

- transport adapter abstraction
- first concrete adapter for the initial radio stack
- operational settings for segment sizing and pacing
- local config and probe workflow for the initial radio stack

Acceptance criteria:

- same artifact and protocol implementation works over the real transport
- radio integration does not change repository or artifact semantics
- the repository contains a concrete integration target rather than a placeholder transport name

## Phase 7: Local Radio Loop Harness

Deliverables:

- repeatable script to start the patched local FreeDATA daemon in test mode
- throwaway sender/receiver repo fixture generation
- end-to-end `OFFER` plus `SEGMENT` dispatch through the live data socket
- receiver-side loopback import, assembly, verification, and apply
- machine-readable summary of final convergence state

Acceptance criteria:

- one command can reproduce the full local loop on a development machine
- the harness proves receiver convergence to the planned target commit
- the harness is suitable as the baseline for future reference-case testing

## Phase 8: Reference-Case Benchmark

Deliverables:

- deterministic fixture generator for a known baseline-to-target repository update
- comparative outputs for naive changed-file archive, `git bundle`, and Longhaul artifact sizing
- configurable segment size and simulated link rate inputs
- machine-readable metrics output suitable for publishing benchmark tables

Acceptance criteria:

- one command produces repeatable before/after transfer metrics
- the scenario uses the same sender and receiver baseline across all compared methods
- the output is simple enough to reuse in documentation and future benchmark automation

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

- what segment size best balances framing overhead versus retransmission waste
- how compact should resume state encoding be on the wire
- whether ref advertisements alone are sufficient for expected real-world histories in v1

These are implementation questions, not architectural blockers. The current design already constrains them to the right solution space.
