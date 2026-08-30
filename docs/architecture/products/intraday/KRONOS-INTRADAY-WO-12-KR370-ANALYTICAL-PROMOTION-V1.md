# KRONOS Intraday WO-12 — KR-370 Analytical Promotion V1

**Status:** APPROVED ARCHITECTURE — BOUNDED ENGINEERING AUTHORIZED

**Identity:** `KRONOS-INTRADAY-WO-12-KR370-ANALYTICAL-PROMOTION-V1`

**Version:** `1.0.0`

**Owner:** `KR-370` / `DOMAIN-003-VALIDATION`

**Authority:** `ANALYTICAL_PROMOTION_ONLY`

**Governing ADR:** [ADR-0020](../../adr/ADR-0020-INTRADAY-WO11-WO12-KR370-ANALYTICAL-PROMOTION-BOUNDARY.md)

**Related boundary:** [ADR-0019](../../adr/ADR-0019-INTRADAY-WO10-WO11-PRE-KR370-SEMANTIC-BOUNDARY.md)

## 1. Purpose

Define the canonical Intraday product architecture for the distinct WO-12
KR-370 analytical-promotion layer after WO-11. This document authorizes bounded
engineering but no real production operation.

The governed sequence is:

```text
Probables V2
  → Review
  → WO-10E / WO-10I / WO-10M
  → WO-11 exact publication
  → WO-12 KR-370 Analytical Promotion
  → only exact current BUY_NOW / SELL_NOW eligible for WO-13
```

WO-10 state is not KR-370 state. WO-11 eligibility is not KR-370 state.
WO-12 performs a new evidence-bound evaluation; it does not rename or remap an
upstream state.

## 2. Common contract reuse

WO-12 reuses without modification:

| Field | Value |
| --- | --- |
| Contract | `KRONOS-KR-370-ANALYTICAL-PROMOTION-V1` |
| Contract version | `1` |
| Owner | `KR-370` |
| Domain | `DOMAIN-003-VALIDATION` |
| State family | `KR370_ANALYTICAL_PROMOTION` |
| Authority | `ANALYTICAL_PROMOTION_ONLY` |

Public states are exactly:

1. `BUY_NOW`
2. `SELL_NOW`
3. `BUY_READY`
4. `SELL_READY`
5. `POTENTIAL_BUY_SETUP`
6. `POTENTIAL_SELL_SETUP`
7. `NO_SETUP`

No duplicate Intraday KR-370 state family is permitted. Intraday request,
evidence, result, persistence and operation contracts remain product-owned and
must bind the common owner/family/version envelope.

## 3. Admission interface

WO-12 consumes only an exact eligible WO-11 member from an exact WO-11
publication. Admission requires:

- the member's WO-11 eligibility is `ELIGIBLE_FOR_DOWNSTREAM_HANDOFF`;
- the bound WO-10 state is `PROMOTION_READY`;
- exact WO-11 publication/member identity and integrity;
- exact WO-10 result identity, integrity and evidence lineage;
- exact Probables V2 run and result;
- exact canonical subject and market family;
- unchanged inherited `LONG` or `SHORT` direction;
- exact analysis boundary and phase;
- exact policy identities, versions, publications and checksums; and
- exact source identities and integrity digests.

Eligibility only admits the member for WO-12 evaluation. It is not a KR-370
classification. Direction mutation, cross-family binding, wrong run, wrong
phase, V1 fallback, corruption, ambiguity or stale unsupported lineage fails
closed.

No latest, mtime, symbol-only or current-market inference is allowed.

## 4. Timeframe authority

| Timeframe | WO-12 treatment |
| --- | --- |
| 1H | Broader Intraday regime and Railway Track context already reconciled upstream |
| 15M | Sole WO-12 KR-370 setup-maturity frame |
| 5M | Excluded; reserved for WO-15 / KR-380 final Entry timing |

WO-12 cannot consume or emit a 5M Entry trigger.

## 5. Criterion grammar

Each criterion result is exactly one of:

- `SATISFIED`;
- `UNSATISFIED`;
- `UNAVAILABLE`.

The denominator is exactly five. There is no K6, score, weight, rank, quota,
family vote or confidence override.

## 6. K1 — 15M directional progression

**Identity:** `K1_15M_DIRECTIONAL_PROGRESSION`

K1 determines whether exact completed governed Intraday 15M structural evidence
is progressing in the inherited direction. Engineering must adapt an existing
governed Intraday 15M fact and preserve its identity, boundary and integrity.

- aligned/progressing governed 15M evidence may produce `SATISFIED`;
- exact governed contrary/non-progressing evidence may produce
  `UNSATISFIED` only where its existing grammar supports that consequence;
- absent, invalid or insufficient evidence produces `UNAVAILABLE`.

K1 performs no Provider call, Chart Analyst operation, LTP-only inference, 5M
inference or copied Swing 1H state evaluation. No progression threshold may be
invented.

## 7. K2 — 15M CPR acceptance

**Identity:** `K2_15M_CPR_ACCEPTANCE`

K2 consumes the already-governed Intraday CPR and exact completed governed 15M
close:

```text
LONG:  completed_15m_close > CPR upper / TC
SHORT: completed_15m_close < CPR lower / BC
```

The comparison is strict. Equality is `UNSATISFIED`, not accepted. Wick,
intrabar high/low, incomplete candle, LTP and 5M evidence cannot satisfy K2.
Missing or invalid CPR/close/boundary evidence produces `UNAVAILABLE`.

If K2 is the sole unsatisfied criterion in an otherwise available READY result,
the evidence contract may preserve the exact factual next condition:

- LONG: completed 15M close above the bound TC level;
- SHORT: completed 15M close below the bound BC level.

This condition has no notification, broker or execution authority.

## 8. K3 — 15M structure-only immediate path clearance

**Identity:** `K3_15M_IMMEDIATE_PATH_CLEARANCE`

K3 determines whether already-governed 15M structural evidence proves an
immediate directional obstruction. Potential evidence includes governed CPR,
PDH/PDL, Classic Pivots, completed 15M barriers and exact structural interaction
facts, but a level merely being ahead is not obstruction.

K3 may produce `SATISFIED` or `UNSATISFIED` only where an existing deterministic
structural predicate proves clear or blocked without adding a threshold. If no
such predicate is available, K3 is `UNAVAILABLE`.

K3 must not use or invent:

- Swing `0.5 × 1H ATR`;
- `0.5 × 15M ATR`;
- a percentage or absolute-distance threshold;
- an ATR-distance threshold;
- Entry, Stop, Target or R:R;
- distance-to-target or profit-potential geometry.

WO-13 owns actual Step-31 geometry.

## 9. K4 — 15M setup quality

**Identity:** `K4_15M_SETUP_QUALITY`

K4 adapts exact existing governed Intraday Native and visual reconciliation
evidence describing 15M setup orderliness, deterioration, contradiction and
development. It does not rerun WO-10, invoke Chart Analyst, create a new Review
or introduce a subjective quality scale.

The adapter must preserve the exact WO-10 evidence/result lineage and may only
derive a criterion consequence explicitly supported by that frozen evidence
grammar. Missing, invalid or inapplicable evidence produces `UNAVAILABLE`.
Swing V3.1 1H setup-quality literals and consequences do not transfer by name.

## 10. K5 — 15M ATR-normalized non-extension

**Identity:** `K5_15M_NON_EXTENSION`

The factual measurement is:

```text
LONG:
  (completed_15m_close - governed_15m_structural_origin) / governed_15m_atr

SHORT:
  (governed_15m_structural_origin - completed_15m_close) / governed_15m_atr
```

The evidence contract may retain:

- `extension_atr_multiple`;
- structural-origin identity and value;
- completed close;
- ATR value, period and calculation identity;
- observation/analysis boundary;
- source evidence identities and integrity; and
- measurement integrity.

The structural origin must be supplied by an existing governed Intraday 15M
contract. Engineering cannot invent or guess it. Missing origin or ATR evidence
makes the measurement unavailable.

### 10.1 Threshold status

`MATERIAL_EXTENSION_THRESHOLD = POLICY_UNRESOLVED`.

No threshold is commissioned. Swing's `>2 × 1H ATR` and any translated
`>2 × 15M ATR` or default are prohibited. K5 consequence remains
`UNAVAILABLE` until a separately governed Intraday threshold is published.

This intentional fail-closed state does not block contract, measurement,
persistence or application engineering. It holds full NOW commissioning.

## 11. Classification

When all five criteria are available:

| Satisfied | LONG | SHORT |
| ---: | --- | --- |
| 5 | `BUY_NOW` | `SELL_NOW` |
| 4 | `BUY_READY` | `SELL_READY` |
| 2–3 | `POTENTIAL_BUY_SETUP` | `POTENTIAL_SELL_SETUP` |
| 0–1 | `NO_SETUP` | `NO_SETUP` |

If any mandatory criterion is `UNAVAILABLE`, the classification is
`NO_SETUP`, hard gate `MANDATORY_K_UNAVAILABLE`, with exact unavailable reason
and evidence lineage. The engine must not count an unavailable criterion as
unsatisfied or calculate a four-of-five result from four available criteria.

## 12. Hard gates

The only universal WO-12 V1 hard gates are:

1. `INVALID_EXACT_EVIDENCE_BINDING`
2. `MANDATORY_K_UNAVAILABLE`
3. `GOVERNING_15M_STRUCTURE_FAILED`
4. `AUTHORITATIVE_GOVERNED_DIRECTIONAL_CONFLICT`

Any hard gate fails closed to `NO_SETUP`. Swing 4H, weekly and 1H
`MESSY_CHOPPY` gates are absent.

## 13. WO-13 eligibility

Only an exact current integrity-valid WO-12 result in `BUY_NOW` or `SELL_NOW`
may be marked eligible for the later WO-13 / Step-31 boundary. All other states
are ineligible.

Eligibility does not construct Entry, Entry Zone, Stop, Target, invalidation,
R:R or quantity. WO-13 remains separately governed and unimplemented by this
architecture publication.

## 14. Contracts authorized for bounded engineering

Bounded engineering may define product-owned contracts equivalent to:

- `KRONOS-INTRADAY-WO12-KR370-REQUEST-V1`;
- `KRONOS-INTRADAY-WO12-KR370-EVIDENCE-V1`;
- `KRONOS-INTRADAY-WO12-KR370-RESULT-V1`;
- an exact batch contract if batch semantics are justified;
- `KRONOS-INTRADAY-CURRENT-WO12-KR370-POINTER-V1`;
- `KRONOS-INTRADAY-WO12-KR370-OPERATION-PROVENANCE-V1`; and
- `KRONOS-INTRADAY-WO12-KR370-POLICY-V1 / 1.0.0`.

Repository naming conventions may refine product contract names without
altering the common KR-370 owner, state family or semantics.

Evidence records preserve exact WO-11/WO-10/Probables lineage, criterion
evidence/results, K5 factual telemetry, hard-gate evidence, policy lineage,
times and integrity. Exact references are preferred over raw evidence
duplication.

## 15. Persistence and application boundary

Authorized persistence is Intraday-owned, immutable and separate from Swing
KR-370 artifacts. It requires content-derived identity, integrity validation,
same-content idempotency, conflicting-rewrite rejection, explicit identity
reload, corruption failure, no mtime/latest authority and an atomic current
pointer written last.

A bounded application may validate a request, reload exact WO-11 sources,
assemble exact evidence, evaluate K1–K5, apply hard gates, classify the common
KR-370 state, persist, write the pointer and explicitly reload. It performs no
Provider acquisition, autonomous Review, Chart Analyst operation or WO-13
construction.

Runtime, control and Browser integration require separately bounded engineering
slices. GET remains inert. This publication does not authorize a real POST or
production WO-12 operation.

## 16. Current population and commissioning state

The current retained real population is:

- `4 × CONTEXT_INCOMPLETE`;
- `0 × PROMOTION_READY`;
- `0 × ELIGIBLE_FOR_DOWNSTREAM_HANDOFF`.

No real WO-12 candidate exists in that batch. Engineering tests may use fully
governed fixtures but cannot manufacture a production candidate.

Architecture and engineering may pass while full NOW commissioning remains
held because K5 is unavailable under unresolved threshold policy.

## 17. Authority exclusions

WO-12 grants no:

- Entry, Entry Zone, Stop, Target, invalidation price or R:R;
- position size or quantity;
- Risk approval;
- Sponsor PAPER/LIVE/IGNORE decision;
- 5M trigger or final Entry timing;
- Entry Outcome;
- broker order, modification or cancellation;
- fill or position authority; or
- production operation by virtue of documentation publication.

## 18. Implementation authorization

ADR-0020 authorizes bounded source engineering for contracts, handoff and
evidence adapters, classification, hard gates, WO-13 eligibility, persistence
and application. Runtime/control/Browser work remains separately sliced.

Implementation must prove exact binding, direction immutability, family
isolation, five-criterion denominator, LONG/SHORT symmetry, unavailable
fail-closed behavior, K3/K5 threshold absence, 5M exclusion, Step-31
eligibility isolation, immutable persistence and Swing regression safety.

No real production WO-12 operation, K5 threshold, WO-13, Risk or KR-380 work is
authorized.

## 19. Deferred decisions

- Intraday K5 material-extension threshold and commissioning evidence.
- Any future distance-based K3 policy; none is required or authorized for V1.
- Runtime/control/Browser composition beyond bounded engineering slices.
- WO-13 geometry, WO-14 Risk and WO-15 final Entry timing.

## 20. Related documents

- [ADR-0020](../../adr/ADR-0020-INTRADAY-WO11-WO12-KR370-ANALYTICAL-PROMOTION-BOUNDARY.md)
- [ADR-0019](../../adr/ADR-0019-INTRADAY-WO10-WO11-PRE-KR370-SEMANTIC-BOUNDARY.md)
- [ADR-0011](../../adr/ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md)
- [KR-370 / KR-380 State-Family Contracts](../../interfaces/KR-370-KR-380-STATE-FAMILY-CONTRACTS.md)
- [WO-10 E/I/M Frozen Architecture](KRONOS-INTRADAY-WO-10-E-I-M-FROZEN-ARCHITECTURE-V1.md)
- [Contract and State Ownership Registry](KRONOS-INTRADAY-CONTRACT-STATE-OWNERSHIP-REGISTRY.md)
- [Deferred Decision Register](KRONOS-INTRADAY-DEFERRED-DECISION-REGISTER.md)
- [Programme Roadmap](KRONOS-INTRADAY-V1-PROGRAMME-ROADMAP.md)

## 21. Revision history

| Date | Version | Change | Authority |
| --- | --- | --- | --- |
| 2026-08-30 | 1.0.0 | Freeze WO-12 KR-370 authority, criteria, handoff, hard gates and implementation boundary | ADR-0020 / Chief Architect / Sponsor |
