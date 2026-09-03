# ADR-0027 — Intraday WO-17 Position Evidence and Active Lifecycle Monitoring

## Metadata

- **ADR Number:** ADR-0027
- **Decision Identity:** `KRONOS-INTRADAY-WO17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-MONITORING-V1`
- **Title:** Intraday WO-17 Position Evidence and Active Lifecycle Monitoring
- **Status:** APPROVED — PUBLICATION PENDING
- **Date:** 2026-09-03
- **Decision Owner:** Sponsor / KRONOS Intraday Engineering Architect
- **Approved By:** Sponsor
- **Decision Scope:** Intraday Product / Platform Interface / Engineering Boundary
- **Authority:** `FACTUAL_POSITION_EVIDENCE_AND_READ_ONLY_LIFECYCLE_MONITORING_ONLY`
- **Engineering Status:** Governance only; WO-17 production source engineering not authorized
- **Runtime / Provider Operation / Position Creation / Broker Authority:** NONE

## Context

[ADR-0026](ADR-0026-INTRADAY-WO16-SPONSOR-DECISION-AND-SESSION-BOUNDED-LIFECYCLE-ADMISSION.md)
ends at an immutable Sponsor PAPER/LIVE/IGNORE choice and a separate admission
disposition. PAPER and LIVE produce `PENDING_POSITION_EVIDENCE`; neither is a
position, fill, execution or monitoring instruction. WO-17 supplies the
separately governed factual position-evidence and read-only lifecycle boundary.

The commissioned Swing implementation demonstrates reusable infrastructure and
patterns for read-only WebSocket observation, continuity, persistence and
Browser presentation. Swing Risk gates, one-lot assumptions, quantities,
economics, product identities, evidence roots, notifications and Journal remain
Swing-owned and are not copied.

## Decision

### 1. Product and authority

The product is
`KRONOS-INTRADAY-WO17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-MONITORING-V1 / 1.0.0`.
Its sole authority is
`FACTUAL_POSITION_EVIDENCE_AND_READ_ONLY_LIFECYCLE_MONITORING_ONLY`.

WO-17 may establish PAPER model-position evidence or Sponsor-attested LIVE
position evidence, observe an active lifecycle, preserve immutable events and
publish notification-worthy facts. It has no broker, order, sizing, monetary
P&L, realised-R, notification-delivery or Journal/Analytics authority.

### 2. Exact upstream admission

WO-17 accepts only a WO-16 `PAPER` or `LIVE` decision with
`PENDING_POSITION_EVIDENCE`. `IGNORE` never enters WO-17.

The exact graph binds WO-13 Trade Plan, WO-14 Risk Observation, WO-15 Timing
Handoff, WO-16 Sponsor Decision, WO-16 Lifecycle Admission, current DOMAIN-008
session, canonical subject and Instrument, and actual MCX contract/roll lineage
when applicable. No upstream fact is recalculated. WO-14 remains advisory and
cannot permit, veto, size, activate, monitor or close a position.

### 3. PAPER entry evidence

A valid PAPER admission creates `PAPER_ARMED`, not a position or fill. Entry
requires two consecutive, ordered and continuous factual observations:

- LONG: previous price is below Entry Reference and current price is at or
  above Entry Reference;
- SHORT: previous price is above Entry Reference and current price is at or
  below Entry Reference.

The first observation establishes a baseline only. Starting beyond the Entry
Reference produces `ENTRY_SEQUENCE_UNRESOLVED`. Duplicate, stale, out-of-order,
mismatched or gap-separated observations cannot manufacture entry. A valid
crossing creates `PAPER_ENTRY_OBSERVED` and `PAPER_ACTIVE`. The price and
timestamp are model evidence, not broker or actual-fill evidence. Quantity,
monetary P&L and realised R remain `UNAVAILABLE`.

### 4. LIVE entry evidence

A valid LIVE admission creates `LIVE_AWAITING_SPONSOR_ENTRY_EVIDENCE`. A LIVE
position exists only after Sponsor attestation provides the exact WO-16
decision/admission identity, exact Instrument or MCX contract, direction,
actual entry price, actual entry timestamp, bounded manual-action provenance
and exact lineage.

A valid attestation creates `LIVE_ENTRY_ATTESTED` and `LIVE_ACTIVE`. It is not
broker acknowledgement, broker fill or exchange confirmation. Quantity,
monetary P&L and realised R remain `UNAVAILABLE`.

### 5. Exact entry cutoffs and supersession

NSE PAPER entry and LIVE entry attestation timestamps must be strictly before
`15:00:00 IST`. MCX equivalents must be strictly before `23:00:00 IST`.
Action at or after the applicable cutoff is rejected. For LIVE, both the actual
entry timestamp and Sponsor-attestation operation timestamp must precede the
cutoff. There is no global cutoff; DOMAIN-008 owns holidays, shortened sessions
and exceptional sessions.

This decision explicitly supersedes older Intraday wording that left exact
NSE `15:00:00 IST` semantics deferred. Existing active positions may still be
monitored to the applicable governed continuous-session boundary.

### 6. Pre-entry invalidation and expiry

WO-13 invalidation factually established before position evidence produces
`ENTRY_INVALIDATED_BEFORE_POSITION`. Expiry of the entry window before position
evidence produces `ENTRY_WINDOW_EXPIRED`. Neither creates a position or an
automatic successor decision; immutable history is retained.

### 7. Position cardinality and lineage

There is at most one non-closed WO-17 position per canonical subject. The
subject-scoped current pointer binds exact Instrument, actual MCX contract,
roll lineage, entry session and lifecycle.

A preserved prior-session non-closed position remains current. A successor
WO-16 decision may coexist as immutable evidence, but cannot activate another
WO-17 position until the prior position closes. Activation fails closed with a
sanitized conflict; neither record is mutated. MCX positions never migrate
automatically to successor contracts or rolls.

### 8. Monitoring transport and identity

After `PAPER_ACTIVE` or `LIVE_ACTIVE`, WO-17 may consume the shared DOMAIN-006
read-only Kite WebSocket. Each observation must bind Provider identity,
canonical subject, Instrument, actual MCX contract where applicable, roll
lineage, session, position, direction and timestamp. Order updates cannot
create lifecycle truth. All WO-17 position, event and history identities remain
Intraday-owned.

### 9. Availability, interruption and recovery

Monitoring availability is separate from position state and uses exactly:
`NOT_APPLICABLE`, `AVAILABLE`, `INTERRUPTED`, `RECOVERING`, `SESSION_ENDED`, and
`UNAVAILABLE`.

Interruption preserves the position, appends an immutable interruption event
and suspends crossing consequences. Recovery appends an event and requires a
fresh factual baseline. Missed crossings are never inferred.

### 10. Stop, Target and invalidation

Levels come unchanged from WO-13. LONG Stop is inclusive at or below Stop and
Target at or above Target. SHORT Stop is inclusive at or above Stop and Target
at or below Target. Invalidation uses only the exact WO-13 contract.

If one observation or a monitoring gap makes Stop and Target both appear
crossed without establishing order, the result is
`LIFECYCLE_EVENT_ORDER_UNRESOLVED`. Facts are preserved; WO-17 does not choose
an order, close automatically or calculate economics. Post-entry invalidation
creates `INVALIDATION_OBSERVED` and does not close PAPER or LIVE.

### 11. Closure

PAPER may close automatically only from an unambiguous ordered Stop or Target
crossing. Closure remains simulated/model evidence and retains model entry,
observed exit, reason, observation lineage and continuity. Manual PAPER closure
is excluded from V1.

Stop, Target and invalidation observations never auto-close LIVE. LIVE closes
only from Sponsor-attested actual exit price/time, bounded manual-action
provenance and exact active-position lineage. This does not claim broker
acknowledgement. Both modes retain quantity, monetary P&L and realised R as
`UNAVAILABLE`.

### 12. Session end

Session end stops monitoring, appends `SESSION_ENDED`, preserves the position
and history, and creates no assumed exit, forced closure or overnight-carry
permission. No automatic later-session reactivation exists. Carry or
revalidation requires successor governance.

### 13. Notification boundary

WO-17 may create immutable notification-worthy events for entry, attestation,
Stop, Target, invalidation, interruption, recovery, unresolved ordering,
session end and closure. It does not deliver Telegram or any notification.
Delivery belongs to WO-18 and notifications never become lifecycle authority.

### 14. Persistence and restoration

Later implementation must use Intraday-owned append-only artifacts, canonical
serialization, SHA-256 integrity, exact replay, conflicting-byte rejection,
nonblocking locks, atomic subject-scoped current pointers, separate
latest-failure aliases, immutable history and successor lineage.

Restoration validates and reconstructs stored state without recalculation.
Restart, outage and recovery cannot manufacture entry, exit, crossings or
lifecycle events. Missing, corrupt or foreign state fails closed.

### 15. Browser boundary

A later slice may extend the Intraday Trade Window to separate WO-13 Trade
Mathematics, advisory WO-14 Risk Observation, WO-15 Timing, WO-16 Decision and
Admission, WO-17 Position Evidence, Monitoring Availability, Active Lifecycle,
immutable history, latest failure, next step and lineage. Detailed UX remains
deferred. Shared Browser infrastructure may be reused; Swing product state is
never shared.

### 16. Reuse classification

Reuse as shared capability is limited to DOMAIN-006 read-only WebSocket and
authenticated runtime, continuity mechanics, Browser/security infrastructure
and atomic persistence primitives. Intraday adapts position separation, PAPER
arming, lifecycle states, crossings, closure, restoration, notification-worthy
events and Trade Window structure. Persistence/event/current-pointer patterns
may be reused as patterns only.

Swing Risk permission, one-lot PAPER, quantity/economics, identities, evidence
roots, notifications, Journal, shadow Step-32 authority, blocked Paper
Observation research, multi-session assumptions and broker authority are not
reused.

### 17. Canonical policy

The canonical payload is
[WO-17 Policy V1](../products/intraday/KRONOS-INTRADAY-WO17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-MONITORING-POLICY-V1.json).
Its SHA-256 is
`4fafb49ef2ffb95c60d53e4061f3658237134c82995db9bd128be99637d38a1a`.

The normative interface is [WO-17 Position Evidence and Active Lifecycle
Monitoring V1](../interfaces/KRONOS-INTRADAY-WO17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-MONITORING-V1.md).
The product record is [WO-17 Position Evidence and Active Lifecycle Monitoring
V1](../products/intraday/KRONOS-INTRADAY-WO-17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-MONITORING-V1.md).

### 18. Engineering sequence

This publication is governance and architecture tests only. It authorizes no
production contracts, runtime, Browser, Provider operation, position,
monitoring or production evidence. Later bounded slices require separate
authorization, beginning with exact upstream binding.

## Consequences

WO-17 can later establish truthful position evidence and lifecycle facts
without confusing models, Sponsor attestations and broker truth. Positions can
survive interruption and session boundaries without invented closure, while
cardinality prevents overlapping positions for one subject.

## Affected Products

- Intraday V1: additive prospective position-evidence/lifecycle architecture.
- Swing V1: unchanged.

## Affected Interfaces

- Adds the Intraday WO-17 Position Evidence and Active Lifecycle Monitoring V1
  architecture contract.
- Consumes WO-13 through WO-16, DOMAIN-001, DOMAIN-006 and DOMAIN-008 without
  changing them.

## Validation Requirements

- Identity, version, authority and policy checksum.
- PAPER/LIVE, cutoff, cardinality, monitoring and closure boundaries.
- Exact upstream binding and WO-14 non-veto.
- Negative authority, architecture indexes and link integrity.

## Validation Evidence

- `tests/unit/architecture/test_adr0027_wo17_position_lifecycle_governance.py`

## Supersedes

Older Intraday wording that deferred exact NSE `15:00:00 IST` entry-cutoff
semantics, and only that wording.

## Superseded By

None.

## Related ADRs

- ADR-0017
- ADR-0022
- ADR-0023
- ADR-0025
- ADR-0026

## Revision History

| Date | Revision | Author | Description | Approval status |
| --- | --- | --- | --- | --- |
| 2026-09-03 | 1.0 | KRONOS Intraday Engineering | Initial position-evidence and active-lifecycle monitoring freeze | Sponsor approved; publication pending |
