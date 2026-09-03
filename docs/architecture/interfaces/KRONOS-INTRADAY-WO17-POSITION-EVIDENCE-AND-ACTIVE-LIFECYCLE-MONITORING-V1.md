# KRONOS Intraday WO-17 Position Evidence and Active Lifecycle Monitoring V1

**Status:** APPROVED ARCHITECTURE CONTRACT — PUBLICATION PENDING

**Version:** `1.0.0`

**Owner:** `KRONOS-INTRADAY`

**Identity:** `KRONOS-INTRADAY-WO17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-MONITORING-V1`

**Authority:** `FACTUAL_POSITION_EVIDENCE_AND_READ_ONLY_LIFECYCLE_MONITORING_ONLY`

**Governing ADR:** [ADR-0027](../adr/ADR-0027-INTRADAY-WO17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-MONITORING.md)

## Purpose

Define the prospective boundary from an exact WO-16 admission to factual PAPER
or LIVE position evidence, read-only lifecycle monitoring and immutable event
history. This is an architecture contract; production record schemas belong to
later separately authorized slices.

## Admission

The complete input graph is:

| Source | Required binding |
| --- | --- |
| WO-13 | Exact immutable Trade Plan and Entry/Stop/Target/invalidation levels |
| WO-14 | Exact plan-bound Risk Observation; advisory and non-veto |
| WO-15 | Exact Timing Handoff and completed-5M lineage |
| WO-16 | PAPER or LIVE Decision plus `PENDING_POSITION_EVIDENCE` admission |
| DOMAIN-008 | Current exact session and applicable market boundary |
| Canonical lineage | Subject, Instrument and exact MCX contract/roll lineage where applicable |

`IGNORE` and `NOT_APPLICABLE_IGNORE` are excluded. No producer fact may be
recalculated or rewritten.

## PAPER state and evidence boundary

PAPER begins as `PAPER_ARMED`. The first observation is baseline only. A later
observation may establish entry only when the pair is consecutive, ordered,
continuous and exactly bound:

- LONG: `previous < Entry Reference` and `current >= Entry Reference`;
- SHORT: `previous > Entry Reference` and `current <= Entry Reference`.

A valid crossing creates `PAPER_ENTRY_OBSERVED` and `PAPER_ACTIVE`. Starting
beyond Entry or losing continuity creates `ENTRY_SEQUENCE_UNRESOLVED`, not a
position. Duplicate, stale, out-of-order, mismatched or gap-separated facts
cannot establish entry.

PAPER entry and closure are simulated/model evidence. They are not fills or
execution. Quantity, monetary P&L and realised R are `UNAVAILABLE`.

## LIVE state and evidence boundary

LIVE begins as `LIVE_AWAITING_SPONSOR_ENTRY_EVIDENCE`. Entry requires one exact
Sponsor attestation containing:

- WO-16 decision/admission identity;
- exact Instrument or MCX contract;
- direction;
- actual entry price and timestamp;
- bounded manual-action provenance; and
- exact upstream/contract/session lineage.

A valid attestation creates `LIVE_ENTRY_ATTESTED` and `LIVE_ACTIVE`. It is not
broker acknowledgement, broker fill or exchange confirmation. Quantity,
monetary P&L and realised R are `UNAVAILABLE`.

## Cutoff contract

| Market | Entry/attestation rule | At cutoff |
| --- | --- | --- |
| NSE | timestamp strictly before `15:00:00 IST` | rejected |
| MCX | timestamp strictly before `23:00:00 IST` | rejected |

For LIVE, both actual-entry and Sponsor-attestation operation timestamps must
precede the cutoff. DOMAIN-008 owns holidays, shortened sessions and exceptional
sessions. Active monitoring may continue through the applicable governed open
session. This contract supersedes only older wording that deferred exact NSE
15:00 cutoff meaning.

## Pre-entry terminal evidence

- exact WO-13 invalidation before position: `ENTRY_INVALIDATED_BEFORE_POSITION`;
- entry window ends before position: `ENTRY_WINDOW_EXPIRED`.

Both preserve history and create no position or automatic successor decision.

## Current-position cardinality

At most one non-closed WO-17 position may exist per canonical subject. The
subject-scoped pointer binds exact Instrument, actual MCX contract when
applicable, roll lineage, entry session and lifecycle.

A prior-session non-closed position remains current. A successor WO-16 decision
may be retained immutably but cannot activate a second position. The conflict
fails closed without mutating either graph. An MCX position cannot migrate to a
successor contract or roll.

## Monitoring observation boundary

The shared DOMAIN-006 read-only Kite WebSocket may transport observations after
activation. Every accepted observation binds Provider identity, canonical
subject, Instrument, actual MCX contract where applicable, roll lineage,
session, position, direction and timestamp. Order updates do not establish
lifecycle truth.

Monitoring availability is independent of position state and is exactly one of:

- `NOT_APPLICABLE`
- `AVAILABLE`
- `INTERRUPTED`
- `RECOVERING`
- `SESSION_ENDED`
- `UNAVAILABLE`

Interruption preserves the position and stops crossing consequences. Recovery
requires an immutable recovery event followed by a fresh factual baseline;
missed crossings are never inferred.

## Lifecycle observations

All levels remain exact immutable WO-13 facts:

| Direction | Stop observed | Target observed |
| --- | --- | --- |
| LONG | price at or below Stop | price at or above Target |
| SHORT | price at or above Stop | price at or below Target |

If one observation or gap implies both without proving order, record
`LIFECYCLE_EVENT_ORDER_UNRESOLVED`, preserve facts and do not close or calculate
an outcome. Post-entry invalidation creates `INVALIDATION_OBSERVED` and does not
close either mode.

## Closure

PAPER closes automatically only from an unambiguous ordered Stop or Target
crossing. Manual PAPER closure is excluded from V1.

LIVE never auto-closes from Stop, Target or invalidation. It closes only from
Sponsor-attested actual exit price/time, bounded manual-action provenance and
exact active-position lineage. Attestation does not claim broker
acknowledgement. Economics remain unavailable for both modes.

## Session end

At session end monitoring stops and `SESSION_ENDED` evidence is appended. The
position and history remain. There is no assumed exit, forced close, overnight
carry permission or automatic later-session reactivation.

## Notification-worthy event publication

WO-17 may publish immutable event facts for PAPER entry, LIVE entry, Stop,
Target, invalidation, interruption, recovery, unresolved order, session end,
PAPER close and LIVE close attestation. Notification delivery belongs to WO-18.
Delivery outcomes cannot create lifecycle truth.

## Persistence and restoration boundary

All records, identities and aliases are Intraday-owned. Later implementation
must preserve append-only immutability, canonical serialization, SHA-256
integrity, exact replay, conflicting-byte rejection, nonblocking locks, atomic
subject-scoped current pointers, separate latest-failure aliases, lifecycle
history and successor lineage.

Restoration validates stored facts without recalculation or Provider calls.
Restart cannot manufacture entry, exit, crossings or events. Corrupt or foreign
state fails closed.

## Explicit negative authority

This interface cannot alter WO-13 geometry, turn WO-14 into permission/veto,
recalculate WO-15 timing, revise WO-16 choice, place or manage broker orders,
size a position, calculate monetary P&L or realised R, deliver notifications,
write Journal/Analytics, authorize carry or force an exit. It cannot read or
mutate Swing product state.

## Future implementation boundary

Exact production dataclasses, event schemas, persistence paths, application
services, monitoring adapters and Browser controls require separately
authorized WO-17 engineering slices. This publication supplies no runtime or
position-creation authority.
