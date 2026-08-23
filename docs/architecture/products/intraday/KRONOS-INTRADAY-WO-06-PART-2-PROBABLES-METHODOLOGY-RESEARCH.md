# KRONOS Intraday V1 — WO-06 Part 2 Probables Methodology Research

**Status:** WO-06 Part-2 engineering review candidate

**Owner:** KRONOS Intraday

**Authority:** Sponsor/EA WO-06 Part 2 of 3
**Production Probables authority:** NONE

## Purpose and current conclusion

Part 2 establishes deterministic, immutable research machinery for comparing
explicit multi-factor qualification variants. It can report which factual
combinations would pass or fail, how populations contract, whether a direction
hypothesis exists, and how ablations affect factual population and later
outcomes. It cannot emit a production Probable, rank a member, choose a trade,
or approve a methodology.

No valid post-activation real Discovery corpus is available. Current evidence
therefore remains `EVIDENCE_PENDING_REAL_DISCOVERY_RUN`, and every methodology
conclusion remains `INSUFFICIENT_EVIDENCE`. Synthetic fixtures prove mechanics
only. They do not establish market usefulness for Narrow CPR or any Long,
Short, neutral, or combined methodology.

## Contract identities

All Part-2 contract versions are `0.1.0`:

| Contract | Identity |
|---|---|
| Methodology research | `KRONOS-INTRADAY-PROBABLES-METHODOLOGY-RESEARCH-V0` |
| Methodology variant | `KRONOS-INTRADAY-PROBABLES-METHODOLOGY-VARIANT-V0` |
| Per-member research result | `KRONOS-INTRADAY-PROBABLE-RESEARCH-RESULT-V0` |
| Methodology comparison report | `KRONOS-INTRADAY-METHODOLOGY-COMPARISON-REPORT-V0` |
| Outcome measurement | `KRONOS-INTRADAY-QUALIFICATION-OUTCOME-MEASUREMENT-V0` |
| Exact real-corpus binding | `KRONOS-INTRADAY-REAL-DISCOVERY-CORPUS-BINDING-V0` |

Every variant identity binds its research contract/version, exact hypothesis
definitions and roles, explicit combination semantics, exact Part-1 corpus,
outcome-definition version, population-diagnostic version, provenance, and
integrity. Display names, arbitrary expressions, `eval`, dynamic code, latest
file selection, scores, ranking, and top-N are absent.

## Research stage model

The framework records, but does not freeze as production policy:

1. factual eligibility;
2. compression/context;
3. higher-timeframe regime;
4. developing Intraday structure;
5. participation;
6. path/extension;
7. directional qualification; and
8. research output.

Each stage records starting population, survivors, bounded rejections,
unavailability, stage retention, stage attrition, and cumulative retention.
Stage order and membership remain research hypotheses for Part 3 to review,
not production semantics.

## Evidence roles and combinations

An explicit hypothesis definition assigns exactly one research role:

- `MANDATORY`: every such hypothesis at the stage must match;
- `SUPPORTING`: the explicit variant may require a bounded count;
- `VETO`: a match rejects the research path;
- `INFORMATIONAL`: recorded without changing qualification.

Only the governed combination
`EXPLICIT_ALL_MANDATORY_ANY_BOUNDED_SUPPORT_EXPLICIT_VETO` is supported. This
is not a generic rule engine. A bounded support count is variant research data,
not a production market threshold.

Research dispositions are only `QUALIFICATION_WOULD_PASS`,
`QUALIFICATION_WOULD_FAIL`, and `QUALIFICATION_UNAVAILABLE`. Every result also
carries `RESEARCH_ONLY_NOT_PRODUCTION_PROBABLE`.

## Hypothesis families

The framework supports exact, versioned hypotheses for:

- previous-session `NARROW_CPR_KGS_V0` compression;
- 1D completed-candle context;
- completed 1H regime;
- completed 15m developing structure;
- completed 5m progression, explicitly not Entry Timing;
- PDH/PDL relationship;
- CPR location, separately from CPR width;
- Classic Pivot P/R1–R4/S1–S4 relationship;
- factual structural barriers, touch, break, close, and retest;
- factual volume/participation comparisons;
- path/room from known reference distances; and
- move/retracement extension.

No family receives a production predicate. Existing facts suffice to represent
these research dimensions. Market discrimination remains unmeasured.

### Narrow CPR roles

Four explicit possibilities are testable without pre-selecting one:

1. mandatory early filter;
2. supporting evidence;
3. one alternative among explicit supporting evidence; and
4. informational/non-useful evidence removable through ablation.

Narrow CPR contributes no direction. Per-session reports preserve factual TRUE,
FALSE, and unavailable counts and show retention after combinations. Its market
usefulness and eventual Probable role remain unresolved.

### Direction

Matched hypotheses may contribute `LONG`, `SHORT`, or no direction. Resulting
research states are `LONG_HYPOTHESIS`, `SHORT_HYPOTHESIS`, `NON_DIRECTIONAL`,
`DIRECTION_CONFLICTING`, or `UNAVAILABLE`. Conflicts are never tie-broken and
Long/Short symmetry is not assumed. Direction is research evidence only.

## Population calibration and ablation

Per-variant reports retain sessions and observations, real/synthetic counts,
mean/median/min/max survivors, retention, zero, `>10`, `>15`, and `>=20`
frequencies, directional distribution, outcome availability, missing evidence,
and bounded conclusions. Zero sessions can raise `STARVATION_RISK`; sessions
above ten can raise `FLOODING_RISK`. Warnings never alter member state or impose
a quota.

Ablation compares an exact base variant with an exact subset variant and
reports the removed hypotheses, population difference, and whether comparable
outcomes exist. No statistical independence claim or universal quality score is
made.

## Factual outcome proposal

Two versioned, non-trading measurement families are proposed:

- expansion: subsequent range expansion and time-to-expansion;
- directional movement: maximum upward excursion, maximum downward excursion,
  and net directional displacement.

Measurements occur strictly after the candidate-formation boundary and remain
separate artifacts. Entry, fill, quantity, P&L, realised R, Stop, Target, and
trade win/loss are prohibited.

Exact materiality thresholds remain unresolved. Candidate normalization options
for later approval are previous-session range and governed pre-observation
move/range facts. Absolute price distance may be retained for directional
arithmetic. ATR is not silently selected.

## No-look-ahead and real-corpus binding

Every hypothesis evidence timestamp must be at or before the observation
boundary. Outcome-marked or later evidence supplied to candidate formation
fails closed. Later outcome-definition versions create new identities and do
not mutate historical measurements.

The future real ingestion seam requires exact:

- Discovery run identity;
- universe publication identity;
- reconciliation publication identity;
- observation boundary; and
- machine-fact bundle identities.

`latest`, `newest`, `current`, directory scans, and automatic runtime ingestion
are prohibited. A later universe or reconciliation publication cannot redefine
historical research.

## Machine-fact status and gaps

Current governed facts are sufficient for the Part-2 research representation.
No shared Platform change is required.

- ATR: `ATR_NOT_REQUIRED_FOR_CURRENT_METHODOLOGY_RESEARCH`. Existing governed
  range/move/retracement facts support the current extension research. ATR need,
  timeframe, and period remain evidence-dependent.
- SMA20/50/200: `SMA_NOT_REQUIRED` for the current framework. No Swing trend or
  SMA methodology is imported.
- volume: existing completed-candle, recent-comparison, session-comparison, and
  factual-ratio telemetry supports research representation. Lookback and
  threshold consequences remain unresolved.
- barrier/path: known references and distances are available, but authoritative
  selection of a nearest or important barrier is not. Any such consequence
  returns `BARRIER_SELECTION_METHODOLOGY_REQUIRED`.

This is not a finding that no enhancement can ever be needed. Real evidence may
later return a precise `MACHINE_FACT_ENHANCEMENT_REQUIRED` register.

## Evidence and Part-3 boundary

Available real sessions: `0`.
Available real observations: `0`.
Synthetic evidence exists only in focused contract tests and is not persisted
as market evidence.

`METHODOLOGY_FREEZE_READY = NO`.

Part 3 requires:

1. one or more explicitly bound, valid post-activation real Discovery runs;
2. approved factual outcome definition/normalization and still-unresolved
   materiality thresholds;
3. population and factual-outcome comparison of explicit variants across
   adequate market conditions, without an invented sample minimum;
4. evidence-backed decisions for mandatory, supporting, veto, informational,
   direction, neutral, barrier, participation, path, and extension treatment;
5. EA/CA methodology-freeze review.

The five current MCX members remain represented as governed prerequisite
unavailable. No contract is selected, no Provider path is fabricated, and they
are not silently removed from universe accounting.

Part 2 introduces no Browser page, notification, Provider acquisition,
authentication, restart, real Discovery operation, Review Analysis, Trade
Construction, Risk, Entry Timing, execution eligibility, or broker mutation.
