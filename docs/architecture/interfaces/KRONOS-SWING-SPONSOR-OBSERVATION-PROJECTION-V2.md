# KRONOS Swing Sponsor Observation Projection V2

**Status:** Approved implementation contract
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

## Journal and Reports handoff boundary

The read-only handoff exposes the four truth families independently: Sponsor
Decision, Sponsor Position/outcome, Paper Track/outcome, and objective
model/outcome. It includes product identity so Swing and Intraday projections
cannot be mixed. Current market price, distance-to-Target, distance-to-Stop,
WebSocket state, and governed current-trading-day routing are presentation-time
fields and are not historical ledger evidence.

Notifications remain outside this contract. A future notification projection
may dismiss presentation without deleting governed evidence, and reactivation
must create a new linked identity rather than mutate expired history.

Notification deletion is presentation dismissal only; it must not delete an
analytical, monitoring, decision, or research source record. Reactivation of an
immutable expired notification may create a new linked LIVE notification only
while the governed source remains current; stale or superseded sources fail
closed. A time-bound Refresh Analysis reminder begins at its governed due
boundary and may update one durable LIVE reminder identity approximately once
per governed hour until a successful fresh analysis or governed expiry resolves
it. Durable reminder-event history is retained; repeated reminder rows are not
manufactured. These are future authority notes, not Notification UX/runtime.

Future Reports may read factual Entry/Exit/P&L from governed Sponsor Position
and closure evidence. Paper Observation Track P&L and actual R are unavailable.
Net-P&L aggregation, win rate, average R, max drawdown, daily P&L, performance
trade counts, and all effectiveness conclusions remain unimplemented analytics
and are not authorized by this projection.
