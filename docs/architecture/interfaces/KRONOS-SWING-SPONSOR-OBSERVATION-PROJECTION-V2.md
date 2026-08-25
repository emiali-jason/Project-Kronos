# KRONOS Swing Sponsor Observation Projection V2

**Status:** Approved architecture contract; runtime not started
**Version:** 2
**Contract identity:** `KRONOS-SWING-SPONSOR-OBSERVATION-PROJECTION-V2`
**Owner:** Swing Sponsor presentation
**Authority:** Read-only projection
**Governing decision:** ADR-0016

## Purpose

This prospective read-only projection keeps three source truths separate:

- Sponsor PAPER Observation Decision;
- Paper Observation Track; and
- governed PAPER Sponsor Position.

It does not version or reinterpret the immutable Sponsor Observation Decision
V1 source record. It joins exact source identities and digests for presentation.

## Required presentation

Where available, the projection exposes Sponsor decision, Step-31 severity and
warnings, decision-time Risk, position activation disposition, Sponsor Position
availability, Paper Track identity/status, Entry-observed state, track outcome,
objective outcome, and Sponsor-position outcome. Unavailable facts remain
explicit.

For blocked PAPER it may present:

```text
SPONSOR DECISION          PAPER
POSITION ACTIVATION       BLOCKED
PAPER OBSERVATION TRACK   AVAILABLE / ACTIVE / COMPLETE
PAPER TRACK OUTCOME       <bounded state>
```

`START PAPER OBSERVATION` is separate from PAPER trade Entry and Position
activation. The projection cannot start a track, position, monitoring session,
objective model, order, or notification and cannot calculate P&L, actual R, or
research performance.

## Trust and history

All source run/instrument/assessment/decision/snapshot/track identities and
digests must match. A mismatch fails closed. Historical V1 projections retain
their original meaning and receive no inferred track.
