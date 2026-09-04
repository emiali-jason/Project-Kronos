# KRONOS Intraday V1 — WO-B Operational Readiness Review

**Status:** APPROVED ARCHITECTURE — PUBLICATION PENDING; WO-B1 ENGINEERING AUTHORIZED

**Title:** Intraday Operational Readiness & Sponsor Review Projection

**Identity:** `KRONOS-INTRADAY-OPERATIONAL-READINESS-REVIEW-V1`

**Version:** `1.0.0`

**Policy:** `KRONOS-INTRADAY-OPERATIONAL-READINESS-REVIEW-POLICY-V1 / 1.0.0`

**Authority:** `READ_ONLY_CROSS_DOMAIN_COMPOSITION`

**Governing ADR:** [ADR-0029](../../adr/ADR-0029-INTRADAY-WO-B-OPERATIONAL-READINESS-REVIEW.md)

## Purpose

WO-B answers which already-governed state each Intraday opportunity occupies
and whether any existing fact is available for Sponsor attention. It composes
authoritative producer facts and never creates or replaces them.

## Snapshot contract

`KRONOS-INTRADAY-OPERATIONAL-READINESS-REVIEW-V1 / 1.0.0` is an immutable,
candidate-scoped snapshot. It binds exact review policy/boundary, candidate and
opportunity, analysis lineage, canonical subject/Instrument, MCX contract where
applicable, source artifact identity/schema/policy/integrity, currentness and
supersession, exact producer state/reason, review classification, bounded
diagnostic, next governed stage, provenance, deterministic identity, and
integrity hash.

WO-B1 defines fixture-driven source references for future composition from:

- Probables/candidate state;
- analytical promotion;
- WO-13 Trade Plan;
- WO-14 advisory Risk Observation;
- WO-15 Timing Handoff;
- WO-16 Sponsor Decision/lifecycle admission;
- WO-17 position/monitoring state;
- DOMAIN-001 Instrument and active-contract identity; and
- DOMAIN-008 session/currentness facts.

No B1 code executes those domains or acquires Provider facts.

## Review classifications

The only review classifications are `NOT_REACHED`, `AVAILABLE`, `WAITING`,
`BLOCKED`, `UNAVAILABLE`, and `TERMINAL`. Each retains the exact producer state,
reason, and source reference. Expected downstream absence may be `NOT_REACHED`;
absence is not otherwise reclassified.

Independent states remain independent. `TIMING_QUALIFIED` may coexist with
`RISK_UNAVAILABLE`. No global readiness boolean, score, vote, or weighted
result exists.

## Persistence

The Intraday-owned namespace is
`intraday-v1/wo-b-operational-readiness-review-v1`. It contains immutable
snapshot history, immutable current-pointer history, candidate-scoped atomic
current aliases, immutable bounded failures, and separate candidate-scoped
latest-failure aliases.

Identical replay is idempotent. Same identity/different bytes, invalid paths,
tampering, foreign bindings, stale required inputs, superseded-as-current
inputs, unsupported versions, corrupt aliases, and foreign pointer targets fail
closed.

The current pointer is projection only. A newer validated snapshot may move it;
a failed or non-newer build cannot destroy the previous valid current pointer.

## Restoration

Restoration validates every persisted wrapper, identity, integrity, policy,
candidate, run, and pointer-to-snapshot binding without recalculation or
external side effects. It never performs Provider authentication/acquisition,
analysis, Risk, Timing, Sponsor, lifecycle, OpenAI, broker, or notification
work.

## Ownership preservation

- WO-13 retains Trade Construction.
- WO-14/DOMAIN-007 retains advisory Risk.
- WO-15/DOMAIN-004 retains Entry Timing.
- WO-16 retains Sponsor Decision and lifecycle admission.
- WO-17 retains position evidence and lifecycle monitoring.
- DOMAIN-001 retains Instrument/active-contract identity.
- DOMAIN-008 retains session/currentness truth.
- DOMAIN-006 retains Provider factual acquisition.

WO-B consumes none of those producers in B1 and may never mutate them.

## Explicit negative authority

Analytical, Discovery/Probables, promotion, Trade Construction, Risk, Entry
Timing, Sponsor Decision, PAPER/LIVE, position, lifecycle mutation,
monitoring/event, Journal/P&L/outcome, notification delivery, Provider
acquisition, execution, order, and broker authority are all `NONE`.

## Swing reuse

`REUSE_PATTERN_ONLY` applies to immutable composition, persistence, pointer,
idempotency, restoration, and fail-closed mechanics. Swing product identity,
state, evidence, analytical/Risk policy, Sponsor/position/lifecycle semantics,
monitoring authority, and broker semantics are not reused.

## Slice boundary

WO-B1 contains architecture, contracts, persistence, restoration, and focused
tests only. WO-B2 live source adapters/composition and WO-B3 Browser/runtime
acceptance remain unauthorized.
