# ADR-0029 — Intraday WO-B Operational Readiness Review

## Metadata

- **ADR Number:** ADR-0029
- **Decision Identity:** `KRONOS-INTRADAY-WO-B-OPERATIONAL-READINESS-REVIEW-V1`
- **Title:** Intraday Operational Readiness & Sponsor Review Projection
- **Status:** APPROVED — PUBLICATION PENDING
- **Date:** 2026-09-04
- **Decision Owner:** Chief Architect / KRONOS Intraday
- **Approved By:** Chief Architect
- **Decision Scope:** Intraday Product Composition / Presentation Boundary
- **Authority:** `READ_ONLY_CROSS_DOMAIN_COMPOSITION`
- **Runtime / Provider / Analytical / Trading / Broker Authority:** NONE

## Context

Intraday owns a governed sequence of producer states from Probables through
analytical promotion, Trade Construction, advisory Risk, Entry Timing, Sponsor
Decision, position evidence, and lifecycle observation. Those producers retain
their semantic ownership. Sponsor review needs one exact, current projection of
the facts without creating a competing analytical decision or lifecycle.

## Decision

### 1. Product boundary

The product is
`KRONOS-INTRADAY-OPERATIONAL-READINESS-REVIEW-V1 / 1.0.0` under policy
`KRONOS-INTRADAY-OPERATIONAL-READINESS-REVIEW-POLICY-V1 / 1.0.0`.

WO-B owns read-only cross-domain composition, exact identity/integrity binding,
freshness and supersession validation, deterministic review classification,
immutable review snapshots, current-projection mechanics, and bounded
diagnostic projection. It is not an analytical engine, trading-readiness
authority, or second lifecycle.

### 2. Producer ownership

Every source-domain state and reason is retained exactly. WO-B never replaces,
reinterprets, or recalculates Probables, promotion, WO-13 Trade Plans, WO-14
Risk Observations, WO-15 Timing Handoffs, WO-16 Sponsor Decisions/admissions,
WO-17 positions/lifecycle facts, DOMAIN-001 identity, or DOMAIN-008 session
truth.

### 3. Snapshot model

Each immutable review snapshot binds its review policy, boundary, candidate or
opportunity, analysis/run lineage, canonical subject and Instrument, actual MCX
contract when applicable, source artifact identities/versions/policies,
integrity identities, currentness and supersession facts, exact producer
states/reasons, review classifications, bounded diagnostics, next governed
stage where derivable, provenance, and its own deterministic identity and
integrity hash.

Unsupported artifacts are never synthesized. Foreign, stale where currentness
is required, superseded-as-current, incomplete, mismatched, or tampered source
bindings fail closed.

### 4. Review classifications

WO-B uses exactly `NOT_REACHED`, `AVAILABLE`, `WAITING`, `BLOCKED`,
`UNAVAILABLE`, and `TERMINAL` as projection-only classifications.

- `NOT_REACHED` means an applicable downstream stage is expectedly absent.
- `AVAILABLE` means an exact compatible current source artifact is available.
- `WAITING` preserves an explicit producer waiting/developing state.
- `BLOCKED` preserves an explicit producer state preventing progression.
- `UNAVAILABLE` means required evidence, integrity, or currentness is absent.
- `TERMINAL` preserves an authoritative terminal producer lifecycle state.

Absence is not inferred as `NOT_REACHED` unless producer-stage semantics make
the absence expected. Review classification never replaces the exact source
state or reason.

### 5. Multiple simultaneous truths

Review snapshots retain independent per-boundary review items. For example,
`TIMING_QUALIFIED` and `RISK_UNAVAILABLE` may coexist. They are not collapsed
into `READY` or `NOT_READY`. There is no global `TRADE_READY` boolean, score,
vote, weight, or readiness classifier.

### 6. Persistence and projection

Snapshots are append-only, canonically serialized, integrity sealed, and
replay-idempotent. Conflicting bytes for one identity fail closed. Historical
snapshots remain immutable.

A candidate-scoped current pointer is an atomic alias to the latest
successfully validated newer snapshot. It has no semantic authority. A failed
or stale later build cannot replace or destroy the previous valid pointer.
Latest bounded failure evidence is retained separately and cannot fabricate a
snapshot.

### 7. Restoration

Restoration validates snapshot, pointer, policy, source identity, and integrity
bindings deterministically. It is inert and performs no analysis, Risk or
Timing evaluation, Sponsor decision, lifecycle transition, Provider
acquisition/authentication, OpenAI call, broker call, or notification delivery.

### 8. Browser boundary

WO-B1 has no Browser or runtime scope. A later separately authorized Browser
projection must be GET/read-only and may only present the governed snapshot,
history, and latest failure. It may not create or change producer-domain state.

### 9. Negative authority

WO-B has no Discovery/Probables, promotion, Trade Construction, Risk, Entry
Timing, Sponsor Decision, PAPER/LIVE, position, lifecycle mutation,
monitoring/event, notification-delivery, Journal/P&L/outcome, Provider
acquisition, execution, or broker authority.

### 10. Reuse boundary

Swing may be reused as a pattern only for immutable composition, atomic current
pointers, append-only persistence, idempotency, restoration, and fail-closed
mechanics. Swing analytical/Risk policy, Sponsor semantics, position/lifecycle
states, monitoring authority, product identity, evidence, and broker semantics
are not reused.

## Consequences

Sponsor review can later show exact multi-stage truth without introducing a
new decision engine. Current projection is reconstructable and failures remain
visible without erasing last-known-valid review evidence.

## Affected Products

- Intraday V1: additive read-only composition foundation.
- Swing V1: unchanged.

## Related records

- [WO-B Product Record](../products/intraday/KRONOS-INTRADAY-WO-B-OPERATIONAL-READINESS-REVIEW-V1.md)
- [Intraday Ownership Registry](../products/intraday/KRONOS-INTRADAY-CONTRACT-STATE-OWNERSHIP-REGISTRY.md)
- [ADR-0022](ADR-0022-INTRADAY-WO12-WO13-STEP31-TRADE-CONSTRUCTION-BOUNDARY.md)
- [ADR-0023](ADR-0023-INTRADAY-DOMAIN-007-ADVISORY-RISK-OBSERVATION-BOUNDARY.md)
- [ADR-0025](ADR-0025-INTRADAY-WO15-KR380-COMPLETED-5M-ENTRY-TIMING-BOUNDARY.md)
- [ADR-0026](ADR-0026-INTRADAY-WO16-SPONSOR-DECISION-AND-SESSION-BOUNDED-LIFECYCLE-ADMISSION.md)
- [ADR-0027](ADR-0027-INTRADAY-WO17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-MONITORING.md)

## Engineering boundary

WO-B1 authorizes only this architecture/product record, immutable contracts,
product-local persistence, current/failure aliases, restoration, and focused
tests. Browser, runtime, live source binding, Sponsor controls, and production
operations remain separately gated.
