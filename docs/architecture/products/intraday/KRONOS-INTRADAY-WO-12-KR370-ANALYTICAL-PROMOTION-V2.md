# KRONOS Intraday WO-12 — KR-370 Analytical Promotion V2

**Status:** APPROVED ARCHITECTURE — ENGINEERING AND BOUNDED RUNTIME AUTHORIZED

**Identity:** `KRONOS-INTRADAY-WO-12-KR370-ANALYTICAL-PROMOTION-V2`

**Version:** `2.0.0`

**Owner:** `KR-370` / `DOMAIN-003-VALIDATION`

**Authority:** `ANALYTICAL_PROMOTION_ONLY`

**Governing ADR:** [ADR-0021](../../adr/ADR-0021-INTRADAY-WO12-FOUR-CRITERION-PROMOTION-AND-WO15-EXTENSION-OWNERSHIP.md)

## Purpose

Define the current Intraday WO-12 successor after exact WO-11 admission. V2
performs a new four-criterion 15M KR-370 evaluation; it does not rename any
WO-10 state or WO-11 eligibility value.

## Common contract

V2 reuses unchanged:

- contract `KRONOS-KR-370-ANALYTICAL-PROMOTION-V1` / version `1`;
- owner `KR-370`;
- state family `KR370_ANALYTICAL_PROMOTION`;
- states `BUY_NOW`, `SELL_NOW`, `BUY_READY`, `SELL_READY`,
  `POTENTIAL_BUY_SETUP`, `POTENTIAL_SELL_SETUP`, `NO_SETUP`.

This reuse does not change Swing. Intraday supplies a product-specific
four-criterion adapter; Swing retains its five-criterion classifier.

## Admission and direction

V2 retains the exact `KRONOS-INTRADAY-WO11-WO12-HANDOFF-V1` admission contract
because its semantics are unchanged. It validates exact WO-11 publication and
member, WO-10 result/evidence, Probables V2 run/result, canonical subject,
market family, analysis boundary, phase, policy bindings and integrity lineage.
Direction remains inherited `LONG` or `SHORT` and cannot be reversed.

## Mandatory criteria

The denominator is exactly four:

1. `K1_15M_DIRECTIONAL_PROGRESSION` — unchanged exact completed governed 15M
   structural progression responsibility.
2. `K2_15M_CPR_ACCEPTANCE` — unchanged strict completed-15M-close comparison:
   LONG above TC/CPR upper; SHORT below BC/CPR lower; equality unsatisfied.
3. `K3_15M_IMMEDIATE_PATH_CLEARANCE` — unchanged structure-only deterministic
   obstruction responsibility; no distance threshold or geometry.
4. `K4_15M_SETUP_QUALITY` — unchanged bounded adapter over existing governed
   Native/visual reconciliation evidence; no new Review or subjective scale.

Each state is `SATISFIED`, `UNSATISFIED` or `UNAVAILABLE`. There is no K5, K6,
weight, score, rank, vote, confidence override or quota.

## Classification

| Satisfied / 4 | LONG | SHORT |
| ---: | --- | --- |
| 4 | `BUY_NOW` | `SELL_NOW` |
| 3 | `BUY_READY` | `SELL_READY` |
| 2 | `POTENTIAL_BUY_SETUP` | `POTENTIAL_SELL_SETUP` |
| 0–1 | `NO_SETUP` | `NO_SETUP` |

Unavailable K1–K4 fails closed to `NO_SETUP` and
`MANDATORY_K_UNAVAILABLE`. Unavailable is not unsatisfied.

## Hard gates

Only:

1. `INVALID_EXACT_EVIDENCE_BINDING`;
2. `MANDATORY_K_UNAVAILABLE`, K1–K4 only;
3. `GOVERNING_15M_STRUCTURE_FAILED`;
4. `AUTHORITATIVE_GOVERNED_DIRECTIONAL_CONFLICT`.

## Extension and 5M boundary

K5 is absent from V2. Published 15M origin, ATR, extension and forward-outcome
facts are supporting research/telemetry for future WO-15 design only. Their
availability has no V2 decision or gate consequence.

5M has no WO-12 authority. Future 5M extension/chase methodology belongs to
WO-15 / KR-380 and remains unresolved.

## WO-13 eligibility

Only exact current `BUY_NOW` or `SELL_NOW` is eligible for WO-13 / Step 31.
Eligibility is not geometry. WO-12 emits no Entry, Stop, Target, invalidation,
R:R, Risk, PAPER/LIVE, execution or broker authority.

## Versioned contracts

- unchanged admission: `KRONOS-INTRADAY-WO11-WO12-HANDOFF-V1`;
- policy: `KRONOS-INTRADAY-WO12-KR370-POLICY-V2 / 2.0.0`;
- request: `KRONOS-INTRADAY-WO12-KR370-REQUEST-V2`;
- criterion: `KRONOS-INTRADAY-WO12-KR370-CRITERION-V2`;
- evidence: `KRONOS-INTRADAY-WO12-KR370-EVIDENCE-V2`;
- result: `KRONOS-INTRADAY-WO12-KR370-RESULT-V2`;
- eligibility: `KRONOS-INTRADAY-WO12-WO13-ELIGIBILITY-V2`;
- pointer: `KRONOS-INTRADAY-CURRENT-WO12-KR370-POINTER-V2`;
- operation: `KRONOS-INTRADAY-WO12-KR370-OPERATION-PROVENANCE-V2`.

V2 uses `wo12-kr370-v2` persistence and a V2 current pointer. V1 remains in
`wo12-kr370-v1`, immutable and independently restorable. V1 is never upgraded
or reclassified in place.

## Runtime and Browser

The Intraday runtime may compose a V2 store, application and runtime service.
Only an explicit Sponsor POST may evaluate. Startup, restart, GET, WO-11
publication and timers are inert. The application consumes only pre-acquired
exact evidence and performs zero Provider calls.

Browser projection may display canonical subject, family, direction, exact
WO-11 source, K1–K4, satisfied count `/ 4`, KR-370 state, hard gates, WO-13
eligibility, boundary and policy/version. It must not display K5/ATR as a
decision factor or any geometry, Risk, timing, Sponsor-position or broker
language.

## Current operational population

The current exact retained WO-11 publication may contain zero eligible members.
That is a valid state and does not authorize upstream reruns or manufactured
candidates.

## Historical compatibility

The V1 architecture, five-K contracts, persistence and test fixtures remain
historical, immutable and readable. They are not current Intraday V2 policy and
do not constrain Swing's independent five-criterion implementation.
