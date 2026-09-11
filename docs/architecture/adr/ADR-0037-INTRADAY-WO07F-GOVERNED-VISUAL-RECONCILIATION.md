# ADR-0037 — Intraday WO-07F Governed Visual Reconciliation

**Status:** Sponsor/EA Approved — Engineering Candidate
**Date:** 2026-09-11
**Owner:** Sponsor / KRONOS Intraday Engineering Architect
**Supersedes:** The Review V2 user interface's direct dispatch into WO-10 only
**Related:** ADR-0019, ADR-0032, ADR-0033, ADR-0034, ADR-0035, ADR-0036

## Decision

KRONOS inserts a separately versioned, deterministic WO-07F analytical layer
between correspondence-qualified Chart Analyst evidence and WO-10. WO-07F
compares the exact current machine Review thesis with the independently
observed visual evidence retained by WO-07E. It produces exactly one of:
`CONFIRMED`, `CONDITIONAL`, `CONTRADICTED`, `INSUFFICIENT`, or
`NOT_RECONCILABLE`.

WO-07F owns neither trade selection nor execution. It cannot change direction,
calculate Entry, Stop, Target, reward/risk, size, or invoke Risk, PAPER, LIVE,
or broker behavior. `CONFIRMED` and `CONDITIONAL` are eligible only for later
WO-10 evaluation. The other outcomes are not eligible.

## Authority and precedence

The input chain is exact and identity-bound:

1. current Probables result and Review cycle;
2. current chart revision;
3. accepted Answer bytes and hash;
4. imported visual evidence;
5. correspondence-qualified chart observation;
6. the machine source identities retained by the Review cycle.

Upstream binding failure produces `NOT_RECONCILABLE`. A qualified hard
contradiction then takes precedence over incompleteness. Otherwise material
incompleteness produces `INSUFFICIENT`, bounded degradation produces
`CONDITIONAL`, and clean sufficiently established evidence produces
`CONFIRMED`.

Q4 `FAILED_OR_RETURNED_THROUGH` is a hard contradiction to the proposed setup
for either direction. Q1 opposing, mixed/congested structure, weak/missing
base, weak/mixed progression, limited/blocked space, and visible extension are
conditions. Q7 and Q8 therefore affect the result and are not decorative.

Q6/Q9 remain inactive when `SELECTED_Q6_Q9_ANCHOR = NOT_ESTABLISHED`.
Lawful `NOT_OBSERVABLE` in that state is neutral. A future machine-selected
anchor may carry a predeclared direction-specific invalidation mapping; WO-07F
must not create that anchor or infer its relationship.

Q10 `MATERIAL_OBSERVATION` affects the result only through a governed
deterministic classification. If no such classification exists, the result is
`INSUFFICIENT`. No LLM or free-text interpretation is allowed.

## MCX boundary

Native MCX visual evidence and the exact machine-selected native contract are
mandatory. Stable family identity remains visual authority; expiry remains
machine authority. NYMEX/COMEX evidence stays
`SUPPORTING_VISUAL_CONTEXT_ONLY` and
`NOT_INDEPENDENTLY_ESTABLISHED`. It may add a bounded condition but cannot
confirm, contradict, or rescue native evidence. NATGAS commissioning remains
`HELD`, including when its analytical outcome is otherwise eligible.

## Persistence and operation

Each result is an immutable, canonically hashed record with an explicit policy
identity/version, ordered machine-readable reasons, exact upstream identities,
and downstream eligibility. A per-cycle pointer is atomically replaced while
prior records remain immutable. Repeating the same input returns
`ALREADY_RECONCILED`; a changed Answer or chart creates a distinct lineage.

Batch reconciliation follows current Review order. Each candidate commits
independently, so one failure does not roll back other lawful results. Status
and restoration are read-only. Reconciliation occurs only on the explicit
Sponsor control.

## Consequences

The current Review page can show truthful per-candidate 07F readiness, outcome,
reason codes, evidence lineage, and later-WO-10 eligibility. Existing WO-10
engines and all later trade/risk/execution semantics remain unchanged.
