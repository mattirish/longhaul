# Reference Case

## Purpose

Use a deterministic baseline-to-target repository update to compare practical pre-Longhaul transfer methods against Longhaul's current planned artifact flow.

The intent is not to prove that Longhaul is already optimal.
The intent is to make tradeoffs visible with a repeatable fixture.

## Default Scenario

The current reference-case generator is [scripts/run-reference-case.sh](/Users/mattirish_1/projects/ham/rfsync/scripts/run-reference-case.sh).

It creates:

- one sender repository
- one receiver repository cloned from the sender baseline
- a text-heavy fixture with dozens of tracked files
- one update commit containing edits, additions, and a rename

It then compares:

- naive `tar.gz` of the changed files
- `git bundle` from baseline to target
- Longhaul's planned Git pack payload
- Longhaul's current protocol message envelopes

The script prints JSON metrics including byte counts and estimated airtime at a configurable link rate.

## Why This Case

This scenario is intentionally plain:

- known shared baseline
- one-way update
- mostly text
- modest churn
- no conflicts

That makes it suitable as the first public "before Longhaul" comparison.

## Current Finding

The current reference case shows two things clearly:

- Longhaul's planned bundle payload is now effectively at `git bundle` parity on the default fixture
- message framing matters enough that it can dominate airtime if it is not compact

The first implementation used JSON envelopes for all protocol messages.
That was useful for debugging, but too expensive for the actual HF target.

Longhaul now uses compact binary framing for `SEGMENT` messages and compressed framing for the remaining protocol messages.

On the default reference case at `2000 bps`, that changed the estimated protocol-message airtime from about `65.0` seconds down to about `23.9` seconds.

On the same fixture, the current payload comparison is roughly:

- `git bundle`: about `3627` bytes
- Longhaul bundle payload: about `3638` bytes

That is still not the end state, but it is the right trend and exactly the kind of improvement this benchmark is meant to force into the open.

So this benchmark now serves two purposes:

- compare Longhaul against practical pre-existing workflows
- measure progress as Longhaul replaces development-friendly framing with a more compact on-air encoding

## How To Use It

Run:

```bash
scripts/run-reference-case.sh
```

Useful inputs:

- `LONGHAUL_SEGMENT_SIZE`
- `LONGHAUL_LINK_BPS`
- `LONGHAUL_REFERENCE_WORKDIR`

Example:

```bash
LONGHAUL_LINK_BPS=2000 LONGHAUL_SEGMENT_SIZE=256 scripts/run-reference-case.sh
```
