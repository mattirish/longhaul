# Longhaul

Longhaul is a hostile-link Git replication system for radio and other extremely low-bandwidth transports.

It exists for links where transmitted bits are the primary scarce resource. On HF, even under favorable conditions, usable throughput may be measured in low thousands of bits per second or worse. At those rates, protocol chatter, repeated negotiation, and unnecessary retransmission are unacceptable overhead.

Longhaul addresses that constraint by keeping normal Git repositories on both ends while replacing Git's native transport behavior with a sender-prepared, resumable, manifest-driven transfer protocol designed for intermittent links.

This repository was originally named `rfsync`. The working product name is now `Longhaul`.

## Problem

Standard Internet-era tools assume too much:

- round trips are cheap
- sessions are stable
- bandwidth is tolerable
- retransmission cost is acceptable
- both peers can stay online long enough to negotiate efficiently

Those assumptions break down on HF and other hostile links.

Git is still useful as the repository model because it already provides:

- content-addressed objects
- versioned history
- compact storage
- strong object identity

What does not fit the problem is the normal Git transport and negotiation model.

Longhaul is therefore not "Git over HF" in the naive sense. It is a custom hostile-link transport for normal Git repositories.

## V1 Scope

Version 1 is intentionally narrow.

- Linux-first implementation
- normal Git repositories on both sides
- known receiver baseline required
- sender-side planning of required objects
- resumable segmented transfer over an unreliable transport
- delayed import and ref update after full verification

V1 is not:

- a transparent replacement for all Git remotes
- general bidirectional file sync
- conflict-resolution software
- a collaborative editing system
- a full deployment/orchestration platform

## Design Priorities

In order:

1. minimize transmitted bytes
2. minimize retransmitted bytes
3. minimize interactive exchanges
4. preserve repository integrity
5. preserve normal Git repository semantics where practical

If a design choice saves engineering effort but increases airtime use, it is usually the wrong choice.

## Mental Model

Longhaul should be thought of as:

- Git-backed state convergence
- sender-prepared update delivery
- resumable object transfer over hostile links

It should not be thought of as:

- rsync over radio
- SSH replacement
- Winlink file attachments with better branding

## Initial Use Cases

- updating a remote source repository over HF
- delivering software changes to a distant Linux machine over intermittent radio links
- exchanging low-churn text-heavy data between known endpoints where airtime dominates every other cost

## Non-Goals For V1

- arbitrary local working tree reconciliation
- stock `git fetch` or `git push` protocol compatibility
- large binary optimization beyond standard Git behavior
- Windows-first support
- mesh or multi-peer replication
- encryption support on amateur-radio links

## Document Map

- [ARCHITECTURE.md](/Users/mattirish_1/projects/ham/rfsync/ARCHITECTURE.md)
- [PROTOCOL.md](/Users/mattirish_1/projects/ham/rfsync/PROTOCOL.md)
