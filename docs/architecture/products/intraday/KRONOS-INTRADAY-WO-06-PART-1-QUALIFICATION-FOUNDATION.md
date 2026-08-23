# KRONOS Intraday V1 — WO-06 Part 1 Qualification Foundation

**Status:** WO-06 Part-1 engineering review candidate

**Owner:** KRONOS Intraday

**Authority:** Sponsor/EA WO-06 Part 1 of 3
**Production Probables authority:** NONE

## Purpose and boundary

Part 1 establishes reproducible qualification research contracts. A
`PROBABLE` is a governed Native Intraday member whose factual evidence satisfies
a later separately commissioned Native Discovery admission methodology and
therefore deserves downstream Review. A Probable is not a trade, Analytical
Promotion, entry readiness, execution eligibility, or Sponsor position.

Part 1 commissions no Probable methodology, direction, score, ranking, quota,
top-N, Promotion, Trade Construction, Risk, Entry Timing or broker authority.
Its permitted state remains methodology-deferred.

## Governed contracts

All initial contract versions are `0.1.0`:

| Contract | Identity |
|---|---|
| Qualification | `KRONOS-INTRADAY-NATIVE-DISCOVERY-QUALIFICATION-V0` |
| Hypothesis | `KRONOS-INTRADAY-QUALIFICATION-HYPOTHESIS-V0` |
| Corpus | `KRONOS-INTRADAY-QUALIFICATION-CORPUS-V0` |
| Observation | `KRONOS-INTRADAY-QUALIFICATION-OBSERVATION-V0` |
| Population diagnostics | `KRONOS-INTRADAY-QUALIFICATION-POPULATION-DIAGNOSTICS-V0` |
| Qualification report | `KRONOS-INTRADAY-QUALIFICATION-REPORT-V0` |
| Factual outcome | `KRONOS-INTRADAY-QUALIFICATION-FACTUAL-OUTCOME-V0` |
| Narrow CPR fact | `KRONOS-INTRADAY-NARROW-CPR-KGS-V0` |

Artifacts use deterministic canonical JSON, content-bound identities and
integrity, explicit version lookup, atomic immutable retention, idempotent
identical writes, conflicting-duplicate rejection and restart reconstruction.
There is no latest-file authority.

## Narrow CPR KGS V0

The numerical source is the previous completed governed Daily candle `H/L/C`:

```text
P                    = (H + L + C) / 3
BC_RAW               = (H + L) / 2
TC_RAW               = (2 × P) - BC_RAW
CPR_BOTTOM           = min(BC_RAW, TC_RAW)
CPR_TOP              = max(BC_RAW, TC_RAW)
CPR_HALF_WIDTH       = abs(P - BC_RAW)
CPR_HALF_WIDTH_PCT   = abs(P - BC_RAW) / C × 100
CPR_TOTAL_WIDTH      = CPR_TOP - CPR_BOTTOM
CPR_TOTAL_WIDTH_PCT  = (CPR_TOP - CPR_BOTTOM) / C × 100
NARROW_CPR_KGS_V0    = abs(P - BC_RAW) < 0.001 × C
```

The inequality is strict. Exactly `0.10%` half-width is false. `BC_RAW` and
`TC_RAW` are both retained because their numerical ordering is not assumed.
The current or incomplete Daily candle is prohibited. The formula has no
08:45 price, Chartink, TradingView or Chart Analyst dependency.

The classification means only previous-session CPR compression. It creates no
volatility claim, breakout, direction, Probable, readiness, buy or sell state.

## Hypothesis and evidence authority

`NARROW_CPR_KGS_V0` is registered as a `QUALIFYING` hypothesis asking whether
previous-session CPR compression materially improves Native Discovery
discrimination. Its current state is
`EVIDENCE_PENDING_REAL_DISCOVERY_RUN`; it is not approved for methodology.
Arbitrary executable hypothesis configuration is prohibited.

Evidence is explicitly one of:

- `REAL_GOVERNED_MARKET_EVIDENCE`; or
- `SYNTHETIC_TEST_FIXTURE`.

Synthetic evidence proves calculation, serialization, population arithmetic,
failure handling and no-look-ahead. It cannot establish market usefulness,
threshold quality, Probable accuracy, or methodology approval.

No post-activation real 93-member Discovery corpus exists. The first real
operation stopped with `PUBLICATION_STALE` before Provider acquisition.
Part 1 therefore concludes only:

- formula: commissioned as deterministic qualification fact;
- Sponsor-specified strict condition: implemented;
- market usefulness: not established;
- Probable consequence: not commissioned;
- directional consequence: none;
- real qualification: `EVIDENCE_PENDING_REAL_DISCOVERY_RUN`.

## No-look-ahead and factual outcomes

Every qualification input used at time `T` must have been available at or
before `T`. Later information may bind only a separately identified factual
outcome record. Leakage into hypothesis formation fails closed.

Factual outcome definitions are versioned and currently may remain
`OUTCOME_DEFINITION_PENDING`. The contract can later carry session range,
excursion, time-to-expansion, continuation, reversal or close-location facts.
It cannot carry entry fill, quantity, P&L, realised R, Stop/Target or trade
win/loss meaning.

## Corpus and population health

The immutable corpus is explicit-session, multi-session and multi-subject. It
binds universe, reconciliation, Discovery/evidence, hypothesis, outcome-window
and population identities. No unnamed examples, spreadsheet authority,
directory order or current-code recalculation can redefine history.

Population diagnostics record factual population, matches, non-matches,
unavailable subjects and factual failures; arithmetic must reconcile exactly.
Reports support mean, median, min/max, distribution, retention, zero-match,
`>10`, `>15`, and `>=20` reporting buckets. These are diagnostic warnings,
never rejection rules. There is no minimum, maximum, fixed quota, top-N,
ranking or score. Starvation and flooding require evidence review, not weak
admission or arbitrary truncation.

Evidence sufficiency remains explicitly unavailable, insufficient,
accumulating, or ready for review. No sample-count threshold is invented.

## Ownership and sequence

WO-06 owns qualification hypotheses, Probables-methodology research, eventual
Probable admission and qualification population diagnostics. WO-12 owns Review
Analysis / Analytical Promotion and may consume the retained Narrow CPR fact;
it does not originate or recalculate it. DOMAIN-004 owns Entry Timing,
DOMAIN-007 owns Risk, and Browser owns presentation only.

The future sequence is factual availability → machine facts → qualification
hypotheses → staged research → Probables → 3V validation → Review. Part 1 ends
before staged research acquires analytical consequence. Part 2 will study
combinations without a predetermined answer. Part 3 may freeze and integrate a
methodology only after sufficient approved evidence. Parts 2 and 3 are not
started by this record.

Current V1/1.0.0 remains immutable at 98 members. The framework is collection
generic and implements no successor-universe contract. The five current MCX
members remain prerequisite unavailable and receive no fabricated production
Narrow CPR observation.
