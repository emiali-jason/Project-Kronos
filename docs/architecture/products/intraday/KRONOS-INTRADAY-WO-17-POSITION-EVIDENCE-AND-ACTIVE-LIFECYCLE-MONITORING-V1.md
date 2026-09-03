# KRONOS Intraday V1 — WO-17 Position Evidence and Active Lifecycle Monitoring

**Status:** APPROVED ARCHITECTURE — PUBLICATION PENDING; SOURCE ENGINEERING NOT AUTHORIZED

**Identity:** `KRONOS-INTRADAY-WO17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-MONITORING-V1`

**Version:** `1.0.0`

**Policy:** `KRONOS-INTRADAY-WO17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-MONITORING-POLICY-V1 / 1.0.0`

**Policy SHA-256:** `4fafb49ef2ffb95c60d53e4061f3658237134c82995db9bd128be99637d38a1a`

**Authority:** `FACTUAL_POSITION_EVIDENCE_AND_READ_ONLY_LIFECYCLE_MONITORING_ONLY`

**Governing ADR:** [ADR-0027](../../adr/ADR-0027-INTRADAY-WO17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-MONITORING.md)

**Interface:** [WO-17 Position Evidence and Active Lifecycle Monitoring V1](../../interfaces/KRONOS-INTRADAY-WO17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-MONITORING-V1.md)

## Purpose

Freeze the factual boundary that follows WO-16 admission. WO-17 may later
establish truthful PAPER model-position or Sponsor-attested LIVE position
evidence and observe its lifecycle through read-only market facts. It does not
create broker or economic truth.

## Exact input

Only PAPER or LIVE plus `PENDING_POSITION_EVIDENCE` enters WO-17. The exact
WO-13, WO-14, WO-15, WO-16, DOMAIN-008 and canonical Instrument/contract/roll
graph is bound. `IGNORE` is excluded. WO-14 is advisory and non-veto.

## PAPER

PAPER begins `PAPER_ARMED`. Two consecutive, ordered and continuous factual
observations must prove the Entry Reference crossing. The first is baseline
only. LONG crosses from below to at/above; SHORT crosses from above to at/below.
A valid pair creates `PAPER_ENTRY_OBSERVED` and `PAPER_ACTIVE`.

Starting beyond Entry, a gap, stale/out-of-order data or lost continuity cannot
manufacture entry and produces `ENTRY_SEQUENCE_UNRESOLVED` where applicable.
After recovery, a new baseline is mandatory. PAPER evidence is model evidence,
not fill or execution evidence.

## LIVE

LIVE begins `LIVE_AWAITING_SPONSOR_ENTRY_EVIDENCE`. Exact Sponsor-attested
entry price/time, manual-action provenance and bound lineage create
`LIVE_ENTRY_ATTESTED` and `LIVE_ACTIVE`. The attestation is not broker
acknowledgement, fill or exchange confirmation.

## Entry cutoffs

NSE entry evidence must be strictly before `15:00:00 IST`; MCX must be strictly
before `23:00:00 IST`. At or after cutoff is rejected. LIVE requires both actual
entry and attestation-operation timestamps before cutoff. DOMAIN-008 owns
exceptional session truth. This freezes and supersedes the older deferred exact
NSE cutoff wording.

## Position cardinality

One canonical subject may have at most one non-closed WO-17 position. The
subject-scoped current pointer binds exact Instrument, actual MCX contract,
roll lineage, entry session and lifecycle. A prior-session non-closed position
remains current and blocks activation of a successor decision. The successor
WO-16 evidence remains immutable. MCX positions cannot migrate automatically.

## Monitoring

After activation, WO-17 may consume the shared DOMAIN-006 read-only Kite
WebSocket with exact observation bindings. Monitoring availability is separate
from position state: `NOT_APPLICABLE`, `AVAILABLE`, `INTERRUPTED`, `RECOVERING`,
`SESSION_ENDED`, or `UNAVAILABLE`.

Interruption preserves the position and suspends crossing consequences.
Recovery requires an event and fresh baseline. Missed crossings are not
inferred; order updates are not lifecycle truth.

## Lifecycle and closure

Stop, Target and invalidation levels remain immutable WO-13 facts. Stop and
Target comparisons are inclusive. Ambiguous same-observation or gap order
produces `LIFECYCLE_EVENT_ORDER_UNRESOLVED` with no automatic close or economic
calculation. Post-entry invalidation is observed but is not a close.

PAPER may auto-close only on an unambiguous ordered Stop or Target crossing.
LIVE closes only from Sponsor-attested actual exit evidence. Manual PAPER close,
LIVE market-triggered close, monetary P&L and realised R are excluded.

## Session end

Session end stops monitoring and appends evidence but does not force-close,
assume an exit, authorize carry or reactivate the position in another session.

## Notifications

WO-17 may publish notification-worthy immutable events. It does not deliver
notifications; WO-18 owns delivery. Notification state is never lifecycle
authority.

## Persistence and restoration

Future implementation will use Intraday-owned immutable artifacts, exact
integrity and replay, nonblocking concurrency, atomic subject-scoped pointers,
separate latest failure, successor lineage and fail-closed restoration. Restart
must never manufacture a lifecycle event.

## Reuse boundary

Shared DOMAIN-006 read-only transport, authenticated context, continuity
mechanics, Browser/security infrastructure and atomic persistence primitives
may be reused. Swing lifecycle/persistence/event/current-pointer mechanisms
require Intraday adaptation or pattern reuse only.

Swing Risk permission, one-lot PAPER, quantity, P&L/R, product identity,
evidence root, notifications, Journal, Paper Observation research, multi-session
policy and broker authority are prohibited from reuse.

## Browser future shape

A later slice may extend the Intraday Trade Window with separate Trade
Mathematics, advisory Risk, Entry Timing, Sponsor Decision/Admission, Position
Evidence, Monitoring Availability, lifecycle, history, latest failure and
lineage sections. UX details and all runtime controls remain separately gated.

## Explicit unavailable facts

WO-17 V1 retains quantity, monetary P&L and realised R as `UNAVAILABLE` for
PAPER and LIVE. It cannot infer broker order, fill or execution state.

## Canonical policy

The canonical policy is
[KRONOS-INTRADAY-WO17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-MONITORING-POLICY-V1.json](KRONOS-INTRADAY-WO17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-MONITORING-POLICY-V1.json).

This record authorizes governance and architecture tests only. Production
contracts, source, persistence, runtime, Browser, position creation, monitoring
and real operations require later bounded authorization.
