# KRONOS Swing Paper Observation Track V1

**Status:** Approved architecture contract; runtime not started
**Version:** 1
**Contract identity:** `KRONOS-SWING-PAPER-OBSERVATION-TRACK-V1`
**Owner:** Swing Paper Observation Track
**Authority:** Non-position research evidence only
**Governing decision:** ADR-0016

## Purpose

This prospective contract observes the factual market path of one exact
Sponsor `PAPER` decision whose governed Sponsor Position activation is blocked.
It creates no position, objective model, Risk permission, fill, P&L, actual R,
order, execution, or broker authority.

## Mandatory lineage

Creation binds immutable identities and SHA-256 digests for:

- Sponsor Observation Decision and decision-time snapshot;
- run, canonical instrument, assessment, direction, and decision timestamp;
- Step-31 Observation Evidence and policy version;
- exact Entry, Stop, Target, invalidation, availability, warnings, severity,
  reward, risk, and R:R state;
- decision-time DOMAIN-007 identity/state/availability;
- blocked activation disposition; and
- track creation timestamp, provenance, policy, contract, and integrity.

The choice must be `PAPER`; activation must be blocked; Sponsor Position must
be absent. Exact duplicate start is idempotent. Foreign, stale-at-creation,
superseded-at-creation, malformed, corrupt, mismatched, or unsupported evidence
fails closed.

## Explicit Sponsor start

The track begins only after `START PAPER OBSERVATION`. A PAPER decision alone
does not start it. Starting the track is `TRACK STARTED` / `OBSERVATION ACTIVE`,
never `POSITION ACTIVATION`.

## States

Track states are `AVAILABLE`, `ACTIVE`, `MONITORING_INTERRUPTED`, `COMPLETE`,
`OUTCOME_NOT_ESTABLISHED`, and `NOT_APPLICABLE_POSITION_ACTIVATED`.

Outcome states are `ENTRY_NOT_OBSERVED`, `ENTRY_OBSERVED`,
`STOP_LEVEL_TOUCHED`, `TARGET_LEVEL_TOUCHED`,
`BOTH_ORDERING_UNRESOLVED`, `EXPIRED`, and `OUTCOME_NOT_ESTABLISHED`.
`EXPIRED` is reserved and cannot be produced until a later expiry policy is
approved.

## Geometry and events

Step-31 Entry is `OBSERVATION_ENTRY_REFERENCE`. It is not a fill or
Risk-approved execution price. Stop, Target, and invalidation remain exact.
GREEN, AMBER, and RED are eligible if trustworthy; geometry is never repaired.

Entry is observed only from the exact directional condition bound by Step-31.
Stop/Target states are factual level touches after Entry is governably observed
and are not win/loss labels. Ordered observations preserve sequence. Completed
candles may prove bounded containment; unfinished candles cannot establish a
final outcome. Multiple relevant levels inside one interval without independent
ordering produce `BOTH_ORDERING_UNRESOLVED`.

## Monitoring and recovery

The contract may consume governed observations through a dedicated Paper Track
consumer of `SharedSwingMonitoringHub`. It must not reuse KR-380 or Sponsor
Position lifecycle authority. Disconnect becomes `MONITORING_INTERRUPTED`;
bounded historical reconciliation may restore facts but never guess ordering.
Restart restores persisted state idempotently and never creates an event.

Later analysis-run supersession does not rewrite or terminate the original
hypothesis. `EXPIRY POLICY UNRESOLVED`; open tracks remain explicit.

## Double-counting and isolation

If a governed PAPER Sponsor Position activates, no separate track is created;
the position lifecycle supplies the primary PAPER outcome relationship. A track
is a relationship on the one Sponsor-decision research row, not a second row.

The track cannot create KR-380, KR-390, Sponsor Position, lifecycle, closure,
LIVE, notification, monetary P&L, actual R, order, fill, or broker evidence.
Historical decisions receive no automatic track or backfill.
