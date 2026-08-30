# KRONOS Intraday V1 - WO-10 Native + Visual Reconciliation

**Status:** Implementation candidate
**Owner:** Intraday
**Contract version:** 1.0.0
**Trading authority:** None

> **Historical-scope notice (2026-08-30):** This document governs the retained
> WO-10 V1 Q1–Q10 implementation and its immutable artifacts. It does not govern
> the frozen WO-10E/WO-10I/WO-10M successor family. The successor architecture
> is [WO-10 E/I/M Frozen Architecture V1](KRONOS-INTRADAY-WO-10-E-I-M-FROZEN-ARCHITECTURE-V1.md),
> governed by [ADR-0019](../../adr/ADR-0019-INTRADAY-WO10-WO11-PRE-KR370-SEMANTIC-BOUNDARY.md).

## Purpose and authority

WO-10 deterministically relates one exact-current Native Probable to the
trusted imported visual evidence for the same Review Cycle. Native and visual
evidence remain separate truth families. Reconciliation may publish typed
relationships, Review state, analytical Readiness and analytical Promotion;
it cannot rewrite either source family or create Entry, Trade Construction,
Risk, PAPER/LIVE, lifecycle or broker authority.

The frozen authority is:

- `KRONOS-INTRADAY-NATIVE-VISUAL-RECONCILIATION-POLICY-V1 / 1.0.0`;
- policy family `POLICY_B_CORE_STRUCTURE`;
- status policy `STATUS_POLICY_2_COMPLETE_IF_CORE_OBSERVED`;
- `KRONOS-INTRADAY-NATIVE-VISUAL-RECONCILIATION-METHODOLOGY-V1 / 1.0.0`.

Every run binds the immutable policy publication and deterministic methodology
checksum. A later policy requires a new version and new reconciliation run;
historical state is never reinterpreted in place.

## Exact-cycle input boundary

An eligible operation requires exact equality across the current Probables
Run/member, Review Cycle, Question Pack/Request, Chart Revision/artifact,
Answer Pack, imported visual evidence, canonical subject and inherited Native
direction. `INVALID`, missing, tampered, mismatched or superseded evidence
fails closed. Instrument name, directory order and mtime have no authority.

Reconciliation performs zero Provider, Discovery, Probables, Answer-import or
Chart Analyst operations. It runs only through the explicit per-cycle
`RECONCILE REVIEW` or candidate-isolated `RECONCILE ALL READY REVIEWS` control.
Browser GET renders persisted state only.

## Frozen Q1-Q10 policy

| Question | Role | Consequence |
|---|---|---|
| Q1 | Informational | Retain the 1D visual context; no blocking, Readiness or Promotion consequence. |
| Q2 | Mandatory core | `OBSERVED + SUPPORTIVE` satisfies core. `OPPOSING` emits `CORE_VISUAL_1H_NOT_SUPPORTIVE`. `MIXED/UNCLEAR` emits `CORE_VISUAL_DIRECTION_AMBIGUOUS` and requires review. Any non-observed status emits `CORE_VISUAL_EVIDENCE_INCOMPLETE`. |
| Q3 | Supporting/adverse non-blocking | `MATERIAL_OVERLAP` emits `ONE_HOUR_MATERIAL_OVERLAP`; other governed observations do not block. |
| Q4 | Mandatory core | As Q2, with opposing condition `CORE_VISUAL_15M_NOT_SUPPORTIVE`. |
| Q5 | Adverse/manual review | Stalling emits `FIFTEEN_MINUTE_CONTINUATION_STALLED`; opposing structure or both emits `FIFTEEN_MINUTE_OPPOSING_STRUCTURE` and requires review. |
| Q6 | Supporting non-blocking | Retained without veto or Entry authority. |
| Q7 | Informational | No path-clearance, R:R or Trade Construction consequence. |
| Q8 | Informational | No wait, do-not-chase or Entry consequence. |
| Q9 | Supporting/manual review | Directional acceptance is supportive; rejection emits `LOCAL_REJECTION_AGAINST_DIRECTION` and requires review. No Entry trigger authority. |
| Q10 | Manual-review escape hatch | Material observation emits `MATERIAL_VISUAL_OBSERVATION_REQUIRES_REVIEW`; free text is retained but never machine-interpreted into another consequence. |

For Q2/Q4, `PARTIAL`, `NOT_VISIBLE`, `UNAVAILABLE`, or illegitimate
`NOT_APPLICABLE` establishes `REVIEW_INCOMPLETE`. For non-core questions those
states remain exact evidence and may emit only
`SECONDARY_VISUAL_EVIDENCE_INCOMPLETE`, which is informational.

## Review, Readiness and Promotion

The Review family is exactly `REVIEW_INCOMPLETE`, `REVIEW_REQUIRED`, and
`REVIEW_COMPLETE`. Incomplete core evidence has precedence. Review-required
conditions are terminal for automatic promotion and create no Sponsor override.
Core opposing evidence can be complete while still not ready.

Readiness is exactly `NOT_READY` or `ANALYTICALLY_READY`.
`ANALYTICALLY_READY` requires `REVIEW_COMPLETE` and both Q2 and Q4 to be
`OBSERVED + SUPPORTIVE`. Promotion is exactly `NOT_PROMOTED` or `PROMOTED`,
and `PROMOTED` is equivalent to analytical readiness. Direction is inherited
unchanged from the Native Probable. WO-10 defines no `NO_SETUP`, `POTENTIAL`,
`BUY/SELL_READY`, or `BUY/SELL/LONG/SHORT_NOW` state.

## Remaining-condition model

The frozen condition classes are:

- blocking: `CORE_VISUAL_1H_NOT_SUPPORTIVE`, `CORE_VISUAL_15M_NOT_SUPPORTIVE`;
- review required: `CORE_VISUAL_DIRECTION_AMBIGUOUS`,
  `FIFTEEN_MINUTE_OPPOSING_STRUCTURE`,
  `LOCAL_REJECTION_AGAINST_DIRECTION`,
  `MATERIAL_VISUAL_OBSERVATION_REQUIRES_REVIEW`;
- evidence incomplete: `CORE_VISUAL_EVIDENCE_INCOMPLETE`;
- adverse non-blocking: `ONE_HOUR_MATERIAL_OVERLAP`,
  `FIFTEEN_MINUTE_CONTINUATION_STALLED`;
- informational: `SECONDARY_VISUAL_EVIDENCE_INCOMPLETE`.

No score, numeric severity, weight, rank, vote, quota or hidden free-text
interpretation exists.

## Persistence, replay and Browser projection

The Intraday-owned artifact contracts are:

- `KRONOS-INTRADAY-NATIVE-VISUAL-RECONCILIATION-FACT-V1 / 1.0.0`;
- `KRONOS-INTRADAY-RECONCILIATION-RUN-V1 / 1.0.0`;
- `KRONOS-INTRADAY-REVIEW-STATE-V1 / 1.0.0`;
- `KRONOS-INTRADAY-READINESS-V1 / 1.0.0`;
- `KRONOS-INTRADAY-ANALYTICAL-PROMOTION-V1 / 1.0.0`;
- `KRONOS-INTRADAY-CURRENT-RECONCILIATION-POINTER-V1 / 1.0.0`.

Artifacts use canonical serialization, content-derived identities, integrity
validation, append-only retention and conflicting-content rejection. The
current pointer is explicit and integrity-bound. Missing or tampered referenced
artifacts fail closed; no latest-file fallback or Browser recomputation exists.
Identical inputs reproduce the same bytes and identity. New Probables, chart,
Question Pack, Answer Pack, visual evidence or policy inputs establish a new
immutable run while retaining history.

The Review card keeps Native context, imported Q1-Q10 visual observations,
typed reconciliation facts, Review/Readiness/Promotion and remaining
conditions visibly separate. It exposes no Entry, Stop, Target or R:R.

## Swing reuse classification

| Swing source | Classification | Intraday treatment |
|---|---|---|
| immutable analytical records and canonical integrity patterns | `SWING IMPLEMENTATION PATTERN - REUSE PATTERN ONLY` | Product-owned Intraday contracts and serialization |
| append-only stores and explicit current pointers | `PLATFORM - REUSE THROUGH ADAPTER` | Product-owned store with the same safe pattern |
| Native Review evidence separation/explainability | `SWING IMPLEMENTATION PATTERN - REUSE PATTERN ONLY` | Separate Native, visual and reconciliation projections |
| Native Readiness predicates and eight-state family | `SWING POLICY - DO NOT COPY` | Frozen two-state Intraday Readiness only |
| KR-370 scoring/classifications/watchability | `SWING POLICY - DO NOT COPY` | No score and only `PROMOTED/NOT_PROMOTED` |
| Swing application lifecycle composition | `SWING IMPLEMENTATION PATTERN - REUSE PATTERN ONLY` | Explicit Intraday control, candidate isolation and restore |

## Downstream boundary

Outcome evidence remains `ABSENT_PENDING`; no accuracy, performance,
profitability, starvation or flooding claim is authorized. PAPER observation
and WO-11 remain separately gated. WO-10 does not start Entry Timing, Trade
Construction, DOMAIN-007 Risk, Sponsor position, lifecycle, notifications,
journal or execution.
