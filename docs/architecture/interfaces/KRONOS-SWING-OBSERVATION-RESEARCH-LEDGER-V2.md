# KRONOS Swing Observation Research Ledger V2

**Status:** Approved implementation contract
**Version:** 2
**Contract identity:** `KRONOS-SWING-OBSERVATION-RESEARCH-LEDGER-V2`
**Owner:** Swing Observation Research
**Authority:** Research evidence only
**Governing decision:** ADR-0016

## Purpose

Version 2 preserves the Version 1 primary unit—one immutable Sponsor
Observation Decision—and adds Paper Observation Track evidence relationships.
It does not migrate or reinterpret Version 1 records.

## One-row population model

Each decision remains one primary row. Append-only relationships may bind:

- Paper Observation Track and its latest factual outcome;
- KR-380 Entry Outcome;
- KR-390 objective model and objective outcome;
- Sponsor Position and Sponsor Position outcome; and
- the immutable decision snapshot, Step-31 evidence, Risk-at-decision, and
  activation disposition already bound by the decision.

A track never creates a second Sponsor-decision row. Activated PAPER uses the
Sponsor Position relationship and cannot also create a Paper Track relationship
for the same decision. Duplicate exact links are idempotent; changed or
mismatched lineage fails closed.

## Projection and export

Read-only projections may expose track availability/status, Entry-observed
state, Stop/Target touch state, ambiguity, objective-outcome availability, and
Sponsor-position-outcome availability. Missing and late evidence remain
explicit. Export must preserve source identities, versions, timestamps,
provenance, and unavailable values.

The ledger must not derive win rate, P&L, actual R, expectancy, performance,
selection efficacy, methodology feedback, or any Production conclusion.

## Persistence and authority boundaries

Records and links are append-only, integrity-bound, restart-restorable, and
deterministically replayable. The ledger does not create source events and is
not an input to Discovery, KR-370, Step-31, DOMAIN-007, KR-380, KR-390, Sponsor
Decision, Sponsor Position, UX-10, or any broker path.

Historical Ledger V1 remains independently readable. No automatic backfill is
permitted. V2 is prospective and retains its own primary-row references and
append-only Track/event/outcome links under the same decision identity.

## Operational handoffs

The stable read-only V2 handoff identifies product (`SWING`), mode, direction,
decision-time Step-31/Risk evidence, Sponsor Position and Paper Track as
separate sources, objective-model state, geometry, completion time, and a
governed trading-date routing result. Current LTP and direction-aware distance
are presentation-time facts only and are never persisted into the ledger.

Trading-day routing consumes DOMAIN-008's governed trading date: active and
current-trading-day completed evidence is Journal-eligible; earlier completed
evidence is Reports/history-eligible. It never deletes or moves source records.

WebSocket status consumes actual `SharedSwingMonitoringHub` connection state.
REST Provider authentication is not WebSocket authority. `IDLE` means no
shared Swing monitoring owner currently requires the transport; required but
not factually connected means `DISCONNECTED`.

Paper Track monetary P/L and actual R remain `UNAVAILABLE`. Existing governed
Sponsor Position/closure accounting is the only position P/L authority.
