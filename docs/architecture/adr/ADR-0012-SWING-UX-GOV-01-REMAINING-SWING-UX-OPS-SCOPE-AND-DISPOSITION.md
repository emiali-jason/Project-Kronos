# ADR-0012 — Remaining Swing UX/OPS Scope and Disposition

## Metadata

- **ADR Number:** ADR-0012
- **Decision Identity:** SWING-UX-GOV-01
- **Title:** Remaining Swing UX/OPS Scope and Disposition
- **Status:** APPROVED
- **Date:** 2026-08-21
- **Decision Owner:** Chief Architect
- **Proposed By:** Sponsor / Swing Engineering Architect
- **Reviewers:** Chief Architect
- **Approved By:** Chief Architect
- **Decision Scope:** Swing Product / Platform Operations
- **Authority Level:** Chief Architect
- **Repository Approval:** Approved in repository
- **Engineering Status:** UX-04 and OPS-01 closed; UX-09 retired; UX-05, UX-06, and UX-07 pending

## Context

The repository contained no authoritative definitions for the remaining Swing
work-order identities UX-04, UX-05, UX-06, UX-07, UX-09, and OPS-01. Current
V3.1, KR-370, Browser, launcher, progression-watch, Step-31, Step-32, active
lifecycle, and Step-33 capabilities made reconstructing purposes from work-order
numbers unsafe. The Chief Architect approved the definitions and dispositions
in this ADR as their sole current meanings.

UX-10 remains a separate, reserved work order and is not authorized here.

## Decision

### UX-04 — Sponsor Explanation

**Status:** CLOSED / SATISFIED

UX-04 provides a concise, version-correct Sponsor explanation of the exact
persisted V3.1/KR-370 analytical decision.

It includes Opportunities classification, Analysis Details explanation,
KR-370 state, direction, missing criteria, hard-gate reason, exact current
run/instrument binding, governed audit evidence, and consistent compact-card
and Analysis Details presentation.

It excludes Step-31, Entry/Stop/Target/R:R, Risk, alerts, Notifications,
execution, and analytical-policy changes.

Acceptance requires Opportunities and Analysis Details to explain the same
exact persisted V3.1/KR-370 record without contradiction. Controlled
verification established exact V3.1 cycle selection, fail-closed version
handling, exact run/instrument binding, consistent KR-370 classification,
missing-criterion and hard-gate presentation, historical V2 isolation, and no
new analytical authority.

### OPS-01 — Runtime Reliability

**Status:** CLOSED / SATISFIED

OPS-01 governs safe Sponsor application startup, canonical-source resolution,
restart, and backend-health recovery.

It includes canonical repository and Python source resolution, exactly one
intended backend, safe stale-backend handling, port release/recovery, health
verification, staged restart outcomes, bounded sanitized diagnostics, and
fail-closed handling of ambiguous source or failed restart.

It excludes Native Analysis, evidence mutation, product policy, Risk,
execution, and broker operations.

Acceptance requires the installed KRONOS application to resolve the canonical
checkout, start the intended backend, stop a proven stale backend safely,
verify process and port release, health-check current source, and fail closed
when repository or restart authority is missing or ambiguous. Controlled
launcher, process-control, and loopback-server verification satisfies these
requirements without interrupting the Sponsor runtime.

### UX-09 — Retired

**Status:** RETIRED / SUPERSEDED BY UX-08 + UX-10

There is no separate UX-09 runtime implementation. UX-08 owns deterministic
progression-watch state. UX-10 owns future notification delivery, including
Browser Notifications and Telegram. UX-09 must not duplicate or blur those
authorities.

### UX-05 — KR-370 to Step-31 Handoff

**Status:** APPROVED / PENDING IMPLEMENTATION

UX-05 is the exact governed transition from Native KR-370 analytical promotion
into the existing Step-31 Trade Construction path. A separate Step-31 handoff
work order must not be created.

Only exact current KR-370 `BUY NOW` and `SELL NOW` records are eligible.
`BUY READY`, `SELL READY`, `POTENTIAL BUY SETUP`, `POTENTIAL SELL SETUP`,
`NO SETUP`, and `NOT EVALUABLE` are ineligible.

The handoff must bind the exact run, canonical instrument, Native assessment,
V3.1 evidence cycle, and KR-370 record/integrity. Stale, mismatched, missing,
unsupported, or ambiguous bindings fail closed.

UX-05 invokes the existing Step-31 boundary but does not manufacture Entry,
Stop, Target, invalidation, R:R, Risk approval, Sponsor Decision, KR-380 Entry
Outcome, or broker execution. Step-31 remains the sole geometry owner.

Acceptance requires that only an exact current KR-370 `BUY NOW` or `SELL NOW`
record can enter Step-31 and that every other KR-370 state is rejected.

### UX-06 — Trade Window

**Status:** APPROVED / PENDING UX-05

UX-06 presents the exact governed trade constructed by Step-31 for a current
KR-370-originated opportunity.

It includes Entry, Stop, Target, invalidation, R:R, Step-31 geometry
provenance, Risk state, existing Sponsor-decision controls where legitimately
available, exact lineage to KR-370/V3.1/current run, and clear unavailable or
fail-closed states.

It does not create construction formulas, change geometry, create Risk or
Sponsor authority, redesign KR-380 timing, deliver notifications, or authorize
broker execution.

Acceptance requires the Trade Window to consume an exact persisted Step-31
record linked to the current KR-370 source and to present downstream state
without manufacturing authority.

### UX-07 — Trade Lifecycle Continuity

**Status:** APPROVED / PENDING UX-05 + UX-06

UX-07 preserves exact Sponsor-visible lineage from the accepted constructed
trade through the downstream Swing lifecycle and journal.

It includes Step-31 source lineage, Step-32/KR-380 state, applicable active
trade lifecycle, closure, Step-33 journal/analytics access, exact
run/instrument/trade identity continuity, and historical/current separation.

It does not create entry-timing, Risk, lifecycle, notification, Telegram,
analytical-policy, or broker-execution authority.

Acceptance requires one governed current-flow record to remain traceable
without identity loss or reinterpretation through:

```text
KR-370
  -> Step-31
  -> Step-32 / KR-380
  -> active lifecycle
  -> closure
  -> Step-33 journal / analytics
```

## Dependency Freeze

- UX-05 has no dependency on UX-06, UX-07, or UX-10.
- UX-06 depends only on UX-05 within this work-order family.
- UX-07 depends on UX-05 and UX-06.
- UX-10 is an independent delivery layer after the core Sponsor lifecycle
  work.
- No undocumented dependency may be added.

## UX-10 Reservation

UX-10 remains the sole future work order for Notifications, promotion alerts,
Browser notification delivery, and Telegram. This ADR does not implement or
authorize UX-10.

The reserved promotion-alert principle is:

- potential or no-setup states produce no promotion alert;
- `BUY READY`/`SELL READY` may be watched only when the sole remaining
  criterion has an exact deterministic governed condition;
- a future `BUY READY`/`SELL READY` to `BUY NOW`/`SELL NOW` transition is a
  high-value UX-10 notification candidate.

## Remaining Sequence

1. UX-05
2. UX-06
3. UX-07
4. UX-10
5. Final Swing end-to-end verification
6. Comprehensive Swing to Intraday handover

UX-04 and OPS-01 are closed. UX-09 is retired. This ADR does not begin any
remaining implementation.

## Authority Boundaries

This decision preserves V3.1, KR-370-E01, KR-370-E02, KR-370-E03, ADR-0011,
`KRONOS-KR-370-ANALYTICAL-PROMOTION-V1`, the KR-370 colour hierarchy, UX-01R,
UX-08 progression watch, historical V2/V3.0 compatibility, and historical
KR-380 Version 1 compatibility.

It does not change Native Discovery, analytical policy, Step-31 geometry,
DOMAIN-007 Risk, Sponsor Decision, KR-380 entry timing, active lifecycle,
Step-33 journal semantics, Production Pine, Intraday, OpenAI authority, or
broker authority.

## Rationale

One decision record gives the six previously undefined work-order identities a
single approved source, closes verified work without artificial runtime
changes, retires a duplicate scope, and freezes the shortest dependency-safe
remaining sequence.

## Alternatives Considered

- **Six separate ADRs:** Rejected because these are one bounded disposition
  decision with one dependency graph.
- **Infer earlier meanings from neighboring IDs:** Rejected because no
  authoritative historical contracts exist.
- **Implement UX-09:** Rejected because it would duplicate UX-08 or encroach on
  reserved UX-10 delivery authority.
- **Create a separate Step-31 handoff work order:** Rejected because UX-05 is
  the approved handoff.

## Consequences

- UX-04 and OPS-01 can be treated as closed without runtime modification.
- UX-09 cannot be activated independently.
- UX-05 is the next authorized implementation scope, but is not implemented by
  this ADR.
- UX-06 and UX-07 cannot begin before their frozen dependencies are complete.
- UX-10 remains separately reserved.

## Validation Requirements

- UX-04 presentation must bind one exact V3.1/KR-370 record across
  Opportunities and Analysis Details and must fail closed on version or
  identity mismatch.
- OPS-01 must prove canonical source resolution, process-owned restart,
  loopback health verification, port release, ambiguity rejection, and
  sanitized failure handling using controlled tests.
- Architecture contracts must retain the ADR-0011 state-family, Step-31, Risk,
  Sponsor, Intraday, Pine, and broker boundaries.
- Production Pine content must remain unchanged.

## Validation Evidence

- UX-04 focused verification: 120 tests passed across
  `tests/unit/browser/test_swing_v3_sponsor_presentation.py`,
  `tests/unit/browser/test_swing_visual_v3_live.py`,
  `tests/unit/browser/test_browser_native_review.py`, and
  `tests/unit/swing/v1/test_analytical_promotion.py`.
- OPS-01 focused verification: 90 tests passed across
  `tests/unit/tools/test_kronos_browser.py`,
  `tests/unit/browser/test_browser_restart_control.py`, and
  `tests/unit/browser/test_browser_server.py`.
- Architecture boundary verification:
  `tests/unit/architecture/test_kr370_adr01_activation.py`.

## Supersedes

No approved ADR. This decision replaces the absence of authoritative scope for
UX-04, UX-05, UX-06, UX-07, UX-09, and OPS-01.

## Superseded By

None.

## Related ADRs

- [ADR-0011 — KR-370 Analytical Promotion and KR-380 Entry Outcome Semantics](ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md)

## Related Documents

- [KR-370 / KR-380 State-Family Contracts](../interfaces/KR-370-KR-380-STATE-FAMILY-CONTRACTS.md)
- [ADL-005 — Alert Architecture](../ADL-005-Alert-Architecture.md)
- [Swing V1 Step-32 Versioned Contracts](../interfaces/SWING-V1-STEP-32-VERSIONED-CONTRACTS.md)
- [Swing V1 Step-33 Outcome and Journal Integration](../products/swing/SWING-V1-STEP-33-OUTCOME-AND-JOURNAL-INTEGRATION.md)

## Revision History

| Date | Revision | Author | Description | Approval status |
| --- | --- | --- | --- | --- |
| 2026-08-21 | 1.0 | Chief Architect / Engineering activation | Approved remaining Swing UX/OPS scope, dispositions, dependencies, closures, and sequence | APPROVED |
