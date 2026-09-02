# KRONOS Intraday V1 — WO-16 Sponsor Decision and Session-Bounded Lifecycle Admission

**Status:** APPROVED ARCHITECTURE — PUBLICATION PENDING; SOURCE ENGINEERING NOT AUTHORIZED

**Identity:** `KRONOS-INTRADAY-WO16-SPONSOR-DECISION-SESSION-BOUNDED-LIFECYCLE-ADMISSION-V1`

**Version:** `1.0.0`

**Policy:** `KRONOS-INTRADAY-WO16-SPONSOR-DECISION-LIFECYCLE-ADMISSION-POLICY-V1 / 1.0.0`

**Policy SHA-256:** `f9ab891659500abad755cdd272527bfd6e406422042b825b209620d934a3ce9c`

**Authority:** `EXPLICIT_SPONSOR_DECISION_AND_FACTUAL_LIFECYCLE_ADMISSION_ONLY`

**Governing ADR:** [ADR-0026](../../adr/ADR-0026-INTRADAY-WO16-SPONSOR-DECISION-AND-SESSION-BOUNDED-LIFECYCLE-ADMISSION.md)

**Interface:** [WO-16 Sponsor Decision and Lifecycle Admission V1](../../interfaces/KRONOS-INTRADAY-WO16-SPONSOR-DECISION-AND-LIFECYCLE-ADMISSION-V1.md)

## Purpose

Record one explicit Sponsor PAPER/LIVE/IGNORE choice against exact current
Intraday evidence and retain a separate factual lifecycle-admission
disposition. WO-16 does not itself create a position or execution fact.

## Exact product boundary

```text
WO-13 immutable Trade Plan
  + WO-14 advisory Risk Observation
  + WO-15 current TIMING_QUALIFIED Handoff
  + WO-15 session binding
  + DOMAIN-008 OPEN session fact
  + canonical Instrument / MCX contract-roll lineage
    -> immutable Sponsor Decision Snapshot
    -> explicit Sponsor Decision
    -> separate Lifecycle Admission disposition
```

No source is recalculated. Provider acquisition is not part of this flow.

## Eligibility

The exact WO-13 plan must be current, non-superseded, integrity-valid and
`GEOMETRY_COMPLETE`. The exact WO-15 handoff must be current,
non-superseded, integrity-valid and `TIMING_QUALIFIED`. The exact WO-14
observation must bind the same plan, but its state cannot permit, veto, size or
rewrite anything.

DOMAIN-008 must establish the same session as currently `OPEN` with
`session_end=false`. Subject, market family, Instrument, direction, setup,
actual MCX contract and roll lineage must agree. An older qualified handoff or
prior session cannot be selected.

## Decision and admission states

Choices are exactly `PAPER`, `LIVE`, and `IGNORE`.

- PAPER -> `PENDING_POSITION_EVIDENCE`
- LIVE -> `PENDING_POSITION_EVIDENCE`
- IGNORE -> `NOT_APPLICABLE_IGNORE`

The decision source is `LOCAL_SPONSOR_BROWSER_ACTION`. V1 stores no invented
person identity, free-text note or Swing reason vocabulary.

Decision receipt and admission are distinct. Position creation is outside
WO-16 V1. IGNORE creates no position and is final only for the exact immutable
lineage.

## Truthfulness

PAPER and LIVE decisions do not establish fill price/time, lots, quantity,
fees, P&L, realised R, order identity or execution state. Every such field is
`UNAVAILABLE` unless a later separately governed actual-position or simulation
contract provides authoritative evidence.

WO-13 Entry/Stop/Target/invalidation remain objective Trade Plan facts. They
cannot be displayed as an actual fill or actual position. No one-lot PAPER
default and no simulated crossing fill is commissioned.

## Session and supersession

Closed, unavailable, mismatched or ended sessions reject the operation before
a decision is created. Historical decisions remain immutable but are not
current after session or upstream supersession.

There is one final decision per exact WO-15 Timing Handoff and at most one
current decision per canonical subject. Exact replay is idempotent; conflicting
content fails closed. A successor plan, handoff, session or MCX roll may create
a new record with explicit predecessor/supersession lineage.

WO-16 performs no forced exit, overnight carry, automatic closure or
economics. Those responsibilities remain deferred.

## Persistence and restoration

The proposed product-local family is:

`Application Support/KRONOS/evidence/intraday-v1/wo16-sponsor-decision-lifecycle-admission-v1`

It contains append-only snapshots, decisions, admissions, operations, invalid
attempts and supersessions. Atomic current-per-subject and latest-failure
aliases are separate. A failure cannot replace a prior valid current decision.

Restoration validates the stored graph only. It does not call Provider,
recalculate prior work, recreate a decision, replay admission, create a
position or start monitoring.

## Browser and operational control

WO-16 requires a dedicated Intraday page after WO-15. Product logic belongs in
Intraday-owned routes/views and should use the stable shared product seam.

The page must show objective plan, advisory Risk, timing, Sponsor decision,
admission, actual-position availability, current state, immutable history and
latest failure as separate sections. It must state that no broker order was
placed.

GET is inert. POST must inherit exact Host/same-origin and Sponsor-work
admission and use exact bounded JSON, strict fields, query rejection,
nonblocking operation admission, sanitized failures, stale-lineage checks,
idempotent replay and conflict rejection.

## Explicit exclusions

WO-16 does not own analysis, geometry, Risk permission/veto, timing,
position sizing, PAPER simulation, LIVE attestation, actual position, Provider
acquisition, monitoring, closure, notification delivery, Journal/Analytics,
P&L, realised R or broker execution.

Swing contracts, policy identities, evidence roots, positions, lifecycle
events, reasons, one-lot behavior and Risk gates are not copied.

## Engineering gates

After publication, each later slice requires separate authorization:

1. contracts and upstream binding;
2. decision/admission application;
3. persistence/restoration;
4. runtime/Browser/control;
5. mutation-free runtime acceptance; and
6. separately authorized genuine Sponsor E2E.

This record authorizes none of those source or runtime stages.

## Canonical policy

The machine-readable policy is
[KRONOS-INTRADAY-WO16-SPONSOR-DECISION-LIFECYCLE-ADMISSION-POLICY-V1.json](KRONOS-INTRADAY-WO16-SPONSOR-DECISION-LIFECYCLE-ADMISSION-POLICY-V1.json).
