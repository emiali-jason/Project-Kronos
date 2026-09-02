# ADR-0026 — Intraday WO-16 Sponsor Decision and Session-Bounded Lifecycle Admission

## Metadata

- **ADR Number:** ADR-0026
- **Decision Identity:** `KRONOS-INTRADAY-WO16-SPONSOR-DECISION-SESSION-BOUNDED-LIFECYCLE-ADMISSION-V1`
- **Title:** Intraday WO-16 Sponsor Decision and Session-Bounded Lifecycle Admission
- **Status:** APPROVED — PUBLICATION PENDING
- **Date:** 2026-09-02
- **Decision Owner:** Sponsor / KRONOS Intraday Engineering Architect
- **Proposed By:** KRONOS Intraday Engineering Architect
- **Approved By:** Sponsor
- **Decision Scope:** Intraday Product / Interface / Engineering Boundary
- **Authority Level:** Product architecture under existing Platform authorities
- **Repository Approval:** Approved for bounded governance publication
- **Engineering Status:** Governance only; WO-16 production source engineering not authorized
- **Runtime / Provider / Position / Broker Authority:** NONE

## Context

[ADR-0022](ADR-0022-INTRADAY-WO12-WO13-STEP31-TRADE-CONSTRUCTION-BOUNDARY.md)
owns immutable Intraday Trade Construction geometry. [ADR-0023](ADR-0023-INTRADAY-DOMAIN-007-ADVISORY-RISK-OBSERVATION-BOUNDARY.md)
makes WO-14 Risk evidence advisory and non-veto. [ADR-0025](ADR-0025-INTRADAY-WO15-KR380-COMPLETED-5M-ENTRY-TIMING-BOUNDARY.md)
owns completed-5M timing and ends at an immutable Timing Handoff with no
Sponsor, position, execution or broker authority.

WO-16A inspected the commissioned Swing Sponsor Decision and lifecycle chain.
The reusable architectural separation is:

```text
Sponsor choice
  -> factual lifecycle-admission disposition
  -> separately governed position evidence
  -> separately governed monitoring and closure
```

Swing policy, state, Risk-permission gates, one-lot PAPER assumptions, simulated
fills, lifecycle records and persistence remain Swing-owned. This ADR freezes
the Intraday successor boundary without changing Swing or any Platform domain.

## Decision

### 1. Product identity and authority

WO-16 is named **KRONOS Intraday V1 — Sponsor Decision and Session-Bounded
Lifecycle Admission**.

Its authority is exactly
`EXPLICIT_SPONSOR_DECISION_AND_FACTUAL_LIFECYCLE_ADMISSION_ONLY`.

WO-16 may retain an explicit human choice and a factual admission disposition.
It is not market analysis, Risk permission, Entry Timing, position creation,
execution, broker acknowledgement, fill evidence, monitoring, closure,
Journal/Analytics, P&L or realised-R authority.

### 2. Exact upstream admission

One WO-16 decision request is admissible only when all of the following are
simultaneously true:

1. the exact current, integrity-valid, non-superseded WO-13 Trade Plan is bound;
2. its geometry state is `GEOMETRY_COMPLETE`;
3. the exact current WO-14 Risk Observation is bound to that plan;
4. the exact current, integrity-valid, non-superseded WO-15 Timing Handoff is
   bound and its state is `TIMING_QUALIFIED`;
5. the exact WO-15 session binding is bound;
6. the DOMAIN-008 fact is available, belongs to the same exchange, trading
   date, session and calendar version, is `OPEN`, and `session_end` is false;
7. canonical subject, market family, Instrument, direction, setup, actual MCX
   contract and roll lineage agree across the full graph; and
8. policy identities, versions and checksums agree with the immutable sources.

WO-16 does not infer a missing Timing Handoff, select an older qualified
handoff, recalculate geometry or timing, or call Provider services.

WO-14 is required as a bound observation record but every valid WO-14 state is
admissible: `RISK_OBSERVED`, `RISK_ALERT`, or `RISK_UNAVAILABLE`. It has no
permission, veto, timing, quantity or Sponsor consequence. `RISK_APPROVED` and
`RISK_REJECTED` are not Intraday WO-16 prerequisites or states.

### 3. Decision vocabulary and authorship

The decision vocabulary is exactly:

- `PAPER`
- `LIVE`
- `IGNORE`

V1 records the source marker `LOCAL_SPONSOR_BROWSER_ACTION` and a timezone-aware
decision timestamp. It does not invent a person identity. It accepts no
free-text note and imports no Swing decision-reason vocabulary.

### 4. Choice, admission and position separation

Decision receipt and lifecycle admission are separate immutable records.

- PAPER and LIVE produce `PENDING_POSITION_EVIDENCE`.
- IGNORE produces `NOT_APPLICABLE_IGNORE`.

No V1 disposition creates a Sponsor Actual Position. PAPER/LIVE intent does not
equal position admission, execution, broker acknowledgement or fill. A later
position boundary must be separately governed and must reference, not rewrite,
the WO-16 decision and admission records.

IGNORE is terminal only for the exact bound Timing Handoff and upstream
lineage. It creates no position and cannot suppress a later successor lineage.

### 5. PAPER and LIVE truth

For PAPER, the V1 facts for fill price, fill timestamp, quantity, fees,
monetary P&L, realised R, order identity and execution state are all
`UNAVAILABLE`. No one-lot default, model-entry fill or observed-tick simulated
fill is authorized.

For LIVE, the same facts are `UNAVAILABLE`. A LIVE decision is not evidence of
manual execution or a broker fill. Sponsor-attested actual-position fields or
broker-factual evidence require a separately approved contract.

### 6. Session boundary

WO-16 is session-bound. A closed, unavailable, mismatched or ended session
cannot create a decision or admission record. Existing immutable decisions
remain historical, but cease to qualify as current once their session or
upstream lineage is no longer current.

WO-16 V1 owns no active position, so it performs no forced exit, overnight
carry, automatic closure or P&L consequence. Those policies remain deferred to
a later position/lifecycle authority.

### 7. Identity, replay, conflict and supersession

There is at most one final decision per exact WO-15 Timing Handoff. An exact
request-identity and exact-byte replay returns the retained result. Different
content for the same request or Timing Handoff fails closed as a conflict.

At most one WO-16 decision is current per canonical subject. A new exact
current WO-13 plan, WO-15 handoff, session or MCX active-contract/roll lineage
may establish a successor decision. The successor explicitly references its
predecessor/supersession lineage; historical records are never mutated.

### 8. Persistence and restoration

WO-16 owns a new product-local evidence family below the commissioned Intraday
evidence root. It does not extend Swing stores or mutate WO-13, WO-14 or WO-15
artifacts.

The storage pattern is append-only immutable snapshots, decisions, admissions,
operations, invalid attempts and supersession records, plus atomic aliases for
current-per-subject and latest failure. A later failure cannot replace a prior
valid current record.

Restoration validates the complete stored identity/integrity graph without
recalculation, Provider access, Sponsor action, admission replay, position
creation or downstream side effects. Missing, corrupt, foreign or stale state
fails closed with a sanitized reason.

### 9. Browser and control boundary

WO-16 owns an Intraday product page and product-owned route/view code. The
stable shared Browser seam is reused; no Swing route or state is shared.

The page separates objective Trade Plan, advisory Risk Observation, Timing
Handoff, Sponsor decision, admission disposition, actual-position facts,
current projection, immutable history and latest failure. Missing actual facts
render `UNAVAILABLE`, never zero or inferred values. Authority copy states that
no broker order was placed.

GET is inert. Any future POST must retain exact Host and same-origin admission,
Sponsor-work admission, JSON content type, required non-empty body, query
rejection, required/extra-field enforcement, a bounded request size,
nonblocking concurrency, sanitized failures, exact lineage validation,
idempotent replay and conflict rejection. The existing shared request limit is
an outer ceiling; implementation may choose a smaller schema-derived limit but
cannot weaken it.

### 10. Contract family

The V1 contract family is:

- `KRONOS-INTRADAY-WO16-SPONSOR-DECISION-SNAPSHOT-V1 / 1.0.0`
- `KRONOS-INTRADAY-WO16-SPONSOR-DECISION-V1 / 1.0.0`
- `KRONOS-INTRADAY-WO16-LIFECYCLE-ADMISSION-V1 / 1.0.0`
- `KRONOS-INTRADAY-WO16-INVALID-OPERATION-V1 / 1.0.0`
- `KRONOS-INTRADAY-CURRENT-WO16-DECISION-V1 / 1.0.0`
- `KRONOS-INTRADAY-WO16-SPONSOR-DECISION-LIFECYCLE-ADMISSION-POLICY-V1 / 1.0.0`

The normative contract is [WO-16 Sponsor Decision and Lifecycle Admission V1](../interfaces/KRONOS-INTRADAY-WO16-SPONSOR-DECISION-AND-LIFECYCLE-ADMISSION-V1.md).
The product record is [WO-16 Sponsor Decision and Session-Bounded Lifecycle Admission V1](../products/intraday/KRONOS-INTRADAY-WO-16-SPONSOR-DECISION-AND-LIFECYCLE-ADMISSION-V1.md).
The canonical policy payload is [WO-16 Policy V1](../products/intraday/KRONOS-INTRADAY-WO16-SPONSOR-DECISION-LIFECYCLE-ADMISSION-POLICY-V1.json).
Its SHA-256 is
`f9ab891659500abad755cdd272527bfd6e406422042b825b209620d934a3ce9c`.

### 11. Future compatibility, not authority

WO-16 records may be referenced by later Intraday position, monitoring,
notification, closure and Journal/Analytics contracts. This compatibility does
not commission those capabilities. Future consumers must preserve WO-16
identity/integrity and cannot backfill or reinterpret historical decisions.

### 12. Engineering sequence

After this governance publication and separate authorization, the minimum
sequence is contracts/upstream binding, decision/admission application,
persistence/restoration, runtime/Browser control, mutation-free runtime
acceptance, then a separately authorized genuine Sponsor E2E operation.

No later slice is authorized by this ADR publication.

## Rationale

The decision adopts the commissioned separation proven in Swing while keeping
Intraday product state and authority independent. It uses the existing
Intraday nonblocking, append-only and current/latest-failure patterns and avoids
turning advisory Risk or timing evidence into execution.

## Alternatives Considered

- Reuse Swing Sponsor/lifecycle records directly — rejected because policy,
  persistence, session and position semantics are product-specific.
- Create a position immediately for PAPER/LIVE — rejected because authoritative
  fill and quantity policy do not exist.
- Make WO-14 a permission gate — prohibited by ADR-0023.
- Permit decisions against non-qualified or expired timing — rejected as stale
  lifecycle entry.
- Combine decision, admission and future position in one record — rejected
  because it would erase authority and truth boundaries.

## Consequences

WO-16 V1 can record truthful Sponsor intent without claiming participation or
execution. A later work order is required before positions, monitoring,
closure, economics, notifications or Journal integration can exist.

## Risks

- Browser language could imply execution unless negative authority is explicit.
- A stale current alias could expose a prior-session decision unless full
  DOMAIN-008 and upstream lineage is revalidated.
- Future position work could accidentally backfill unavailable facts.
- A shared Browser change could create Swing collision; product-owned routing
  remains the default.

## Affected Products

- Intraday V1: additive Sponsor-decision/admission architecture.
- Swing V1: unchanged.

## Affected Interfaces

- Adds the Intraday WO-16 Sponsor Decision and Lifecycle Admission V1 contract.
- Consumes WO-13, WO-14, WO-15, DOMAIN-001 and DOMAIN-008 without changing them.

## Implementation Implications

Documentation and architecture-test publication only. Production source,
runtime, Provider operations, Sponsor operations and broker operations remain
unauthorized.

## Validation Requirements

- Exact identity/version/authority checks.
- Exact upstream and session-binding checks.
- Risk non-veto and position/broker negative-authority checks.
- PAPER/LIVE unavailable-truth checks.
- Replay, conflict, supersession, persistence and restoration checks.
- Governance-index and link integrity checks.

## Validation Evidence

- `tests/unit/architecture/test_adr0026_wo16_sponsor_decision_governance.py`

## Supersedes

None.

## Superseded By

None.

## Related ADRs

- ADR-0011
- ADR-0015
- ADR-0022
- ADR-0023
- ADR-0025

## Revision History

| Date | Revision | Author | Description | Approval status |
| --- | --- | --- | --- | --- |
| 2026-09-02 | 1.0 | KRONOS Intraday Engineering | Initial Sponsor-decision and session-bounded lifecycle-admission freeze | Sponsor approved; publication pending |
