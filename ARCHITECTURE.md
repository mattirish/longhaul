# Architecture

## System Definition

Longhaul is a hostile-link replication engine for normal Git repositories.

The system goal is to converge a receiver from a known Git baseline to a target Git ref while minimizing airtime, minimizing retransmission, and tolerating intermittent sessions that may span days.

## Governing Constraint

The system is built around one rule:

Transmitted bits are the primary scarce resource.

CPU, RAM, and local disk are generally cheaper than airtime. The architecture therefore pushes planning, object selection, packaging, and verification off the link wherever possible.

## Core Assumptions

- transport throughput may be extremely low
- links may be interrupted frequently
- sessions may be short and irregular
- control traffic should be compact and infrequent
- both endpoints can store a normal Git repository
- the receiver can identify a known baseline commit or tracked ref

## V1 Boundary

V1 is scoped to one repository replicated between known endpoints.

The system is optimized for:

- text-heavy source trees
- predictable history
- fast-forward style convergence from a known baseline

The system does not attempt to solve:

- arbitrary divergent history reconciliation
- dirty working tree synchronization
- user-facing collaborative merge workflows

## Layered Model

### 1. Repository Layer

Both endpoints maintain standard Git repositories.

Git remains the source of truth for:

- commits
- trees
- blobs
- refs
- object integrity

This preserves compatibility with ordinary local Git tooling and avoids inventing a new repository model.

### 2. Planning Layer

The sender computes what the receiver needs based on the receiver's advertised baseline and the desired target ref.

This layer is responsible for:

- identifying the target object closure
- minimizing transmitted objects
- preparing a transport artifact before airtime is used

This work must happen before transmission whenever possible.

### 3. Artifact Layer

The selected Git payload is wrapped in a Longhaul transfer artifact.

The artifact adds:

- explicit identity
- segmentation
- per-segment verification
- whole-artifact verification
- resume metadata

Git-native content is preserved inside the artifact, but the artifact is what the transport layer sees.

### 4. Session Layer

The session layer handles:

- state advertisement
- artifact offers
- segment transfer
- missing-range reporting
- completion reporting

The session layer must be sparse in control traffic and tolerant of pauses between sessions.

### 5. Transport Adapter

The transport adapter moves opaque Longhaul protocol messages.

The sync engine must not assume a specific modem or radio stack. HF radio via FreeDATA is the initial target, but the architecture should remain transport-neutral.

## Why Not Native Git Protocol

Native Git transport is the wrong fit because it assumes:

- interactive negotiation
- tolerable round-trip cost
- reasonably stable sessions

Those assumptions fail on hostile low-rate links. Longhaul keeps Git repositories and Git objects, but replaces the on-air session and transfer behavior.

## Receiver Baseline Model

V1 requires a known receiver baseline.

The receiver advertises compact repository state, typically:

- repository identifier
- node identifier
- tracked refs
- current commit hashes
- incomplete artifact status, if any

V1 does not require a full object inventory advertisement. That would often cost too much airtime relative to the likely savings.

## Transfer Model

The sender computes a Git-native payload containing exactly the required objects to move the receiver from its known baseline to the target ref.

That payload is split into fixed or bounded-size segments and transmitted over one or more sessions.

The receiver:

- stores verified segments durably
- reports only missing ranges or compact receipt state
- verifies the completed artifact
- imports the payload into the local Git repository
- updates refs only after successful verification

## Integrity Model

Integrity is checked at multiple levels:

- Git object integrity inside the repository model
- per-segment hash verification during transfer
- whole-artifact hash verification before import
- ref update only after successful import

The design is transactional in spirit: incomplete or partially corrupted transfer state must not mutate repository refs.

## Failure Model

Expected failures include:

- session interruption
- duplicate segment delivery
- partial artifact receipt
- lost control messages
- corrupted segments

The system must recover by:

- persisting received segments
- ignoring valid duplicates
- requesting only missing ranges
- resuming across long delays

## Bidirectional Future Direction

The long-term project vision may include two-way replicated user-facing folders or document exchange over hostile links.

That future should be built on top of this engine, not folded into the core prematurely.

The engine should therefore remain:

- deterministic
- repository-centered
- transport-agnostic
- explicit about ownership and baseline state

## Initial Implementation Path

Build in this order:

1. local artifact creation from baseline ref to target ref
2. local artifact import into another repository
3. segmented transfer and resume behavior using a file-backed mock transport
4. control message flow for state advertisement and retransmission
5. real transport adapter integration
