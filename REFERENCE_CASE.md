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

The first useful result from this reference case is architectural, not promotional:

- Longhaul's planned pack payload is in the same general class as other Git-native delta packaging methods
- Longhaul's current JSON message envelopes are too expensive to be the final on-air framing

That is expected at this stage. The current message format is debug-friendly and transport-transparent.
It is not yet airtime-efficient enough for the real HF target.

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
