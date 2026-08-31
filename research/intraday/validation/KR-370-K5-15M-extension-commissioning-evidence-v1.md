# KRONOS Intraday WO-12 K5 15M Extension Commissioning Evidence V1

**Artifact identity:** `KRONOS-INTRADAY-WO12-K5-15M-EXTENSION-COMMISSIONING-EVIDENCE-V1`

**Version:** `1.0.0`

**Status:** `INSUFFICIENT_EVIDENCE`

**Authority:** Research evidence only. This artifact does not select or
commission a K5 threshold, change WO-12 policy, or authorize a production
operation.

**Repository boundary:** `3384429f89839620612256870e490e895a445148`

## Research question

At what 15M ATR-normalized extension does an otherwise valid Intraday
directional setup begin to show materially worse continuation quality?

The retained evidence cannot answer this question yet. The audit found no
observation satisfying the complete K5 research eligibility contract. The
result is therefore an evidence-gap finding, not evidence for or against any
candidate threshold.

## Sources inspected

The analysis used only retained, immutable local evidence. It made zero
Provider calls and performed no runtime operation.

1. `INTRADAY-QUALIFICATION-CORPUS-f70fadc6b256f3e6d5424598228c73e352684e2e789ba328de56c69f0cf5029f`,
   corpus version `0.2.0`, integrity
   `INTEGRITY-QUALIFICATION-CORPUS-f70fadc6b256f3e6d5424598228c73e352684e2e789ba328de56c69f0cf5029f`.
   Its source file SHA-256 is
   `85b66542b809564289a0acf45b454ece53dcecf600268dc2890ef4af0ff897fc`.
2. 465 `KRONOS-INTRADAY-SEMANTIC-QUALIFICATION-EVIDENCE-V1`
   artifacts bound one-to-one to the corpus observations.
3. 47,945 complete governed historical candle payloads: 465 `1D`, 2,800
   `1H`, 11,170 `15M`, and 33,510 `5M`, spanning 93 subjects and the five
   sessions from 2026-08-17 through 2026-08-21.
4. 32 retained structural-evidence documents, including eight `15M`
   documents. These documents cover only `RELIANCE`; their barrier origins
   are all `1D`, and they contain local-relation facts but no governed K5
   structural-origin selection.
5. Retained V1/V2 Probables, completed-evidence, reconciliation, and
   qualification-research stores were inspected for structural-origin, ATR,
   and outcome fields. None supplied a complete K5 observation.

The older corpus version `0.1.0` was not combined with version `0.2.0`; its
395 observations are predecessors represented by the later governed corpus,
so combining them would double-count logical subject-session observations.

## Eligibility and no-look-ahead method

A qualified observation required all of the following at its analysis
boundary:

- exact subject and market family;
- exact LONG or SHORT direction;
- governed 15M structural-origin identity and value;
- completed 15M close;
- governed 15M ATR value, period, and calculation identity;
- analysis boundary and exact provenance; and
- a subsequent completed-candle path with a governed outcome definition
  sufficient to measure MFE, MAE, continuation, deterioration/failure, and
  elapsed completed 15M bars.

Future candles were not used to manufacture boundary facts. No local pivot,
barrier, ATR period, ATR smoothing convention, forward horizon, or
continuation/failure predicate was selected by this research operation.

## Population accounting

| Population | Count |
| --- | ---: |
| Retained real observations considered | 465 |
| NSE equity observations | 455 |
| NSE index observations | 10 |
| MCX observations | 0 |
| Qualified K5 observations | 0 |

The retained 15M structure fact in each considered observation reported:

| 15M factual direction | All | NSE equity | NSE index |
| --- | ---: | ---: | ---: |
| LONG | 51 | 47 | 4 |
| SHORT | 165 | 161 | 4 |
| NON_DIRECTIONAL | 249 | 247 | 2 |

These counts describe existing factual 15M structure only. They are not a K5
setup-direction population, because no observation reached K5 eligibility.

## Exclusions

Exclusion reasons overlap and therefore must not be summed:

| Reason | Affected observations | Evidence |
| --- | ---: | --- |
| Governed 15M structural origin unavailable | 465 | No retained evidence artifact contains `structural_origin_identity` or `structural_origin_value`; the structural store does not select an origin for K5. |
| Governed 15M ATR unavailable | 465 | No retained evidence artifact contains `atr_value`, `atr_period`, or `atr_calculation_identity`; the Intraday ATR period/calculation remains ungoverned. |
| Governed subsequent outcome unavailable | 465 | Every corpus observation has `subsequent_outcome_identity = null`. |
| Exact LONG/SHORT 15M structure absent | 249 | The retained 15M structure fact is `NON_DIRECTIONAL`. |
| MCX family evidence absent | Entire MCX family | The exact corpus has zero MCX observations; NATGAS remains held and no MCX member was substituted. |

Although complete 15M candles exist, calculating an ATR would require choosing
an ungoverned period and smoothing convention. Although local-high/local-low
facts exist for a small RELIANCE-only structural store, selecting one as the
K5 origin would create a new analytical rule. Although later candles exist for
some early sessions, choosing a future horizon and declaring continuation or
failure would create an ungoverned outcome methodology. All three actions are
outside this work order.

## Extension distribution and outcome analysis

No `extension_atr_multiple` can be calculated without both a governed origin
and governed ATR. Therefore all descriptive bins are `NOT_ESTIMABLE`:

| Research bin | Qualified sample | Continuation | Deterioration/failure |
| --- | ---: | --- | --- |
| `<0.75 ATR` | 0 | NOT_ESTIMABLE | NOT_ESTIMABLE |
| `0.75–1.00` | 0 | NOT_ESTIMABLE | NOT_ESTIMABLE |
| `1.00–1.25` | 0 | NOT_ESTIMABLE | NOT_ESTIMABLE |
| `1.25–1.50` | 0 | NOT_ESTIMABLE | NOT_ESTIMABLE |
| `1.50–1.75` | 0 | NOT_ESTIMABLE | NOT_ESTIMABLE |
| `1.75–2.00` | 0 | NOT_ESTIMABLE | NOT_ESTIMABLE |
| `2.00–2.50` | 0 | NOT_ESTIMABLE | NOT_ESTIMABLE |
| `>2.50` | 0 | NOT_ESTIMABLE | NOT_ESTIMABLE |

No MFE, MAE, bars-to-continuation, bars-to-failure, setup type, or outcome
rate is reported. Recording any of them here would require an ungoverned
definition or a fabricated binding.

## Candidate cut-point sensitivity

| Candidate cut | Below | Above | Outcome comparison | ±0.25 sensitivity |
| ---: | ---: | ---: | --- | --- |
| 1.00 ATR | 0 | 0 | NOT_ESTIMABLE | NOT_ESTIMABLE |
| 1.25 ATR | 0 | 0 | NOT_ESTIMABLE | NOT_ESTIMABLE |
| 1.50 ATR | 0 | 0 | NOT_ESTIMABLE | NOT_ESTIMABLE |
| 1.75 ATR | 0 | 0 | NOT_ESTIMABLE | NOT_ESTIMABLE |
| 2.00 ATR | 0 | 0 | NOT_ESTIMABLE | NOT_ESTIMABLE |
| 2.25 ATR | 0 | 0 | NOT_ESTIMABLE | NOT_ESTIMABLE |
| 2.50 ATR | 0 | 0 | NOT_ESTIMABLE | NOT_ESTIMABLE |

The retained evidence gives no independent Intraday support for Swing's
2 ATR rule and does not reject it. Copying 2 ATR would remain prohibited.

## Stability, family, direction, and phase findings

- Common versus family-specific threshold: `INSUFFICIENT_EVIDENCE`.
- Equity/index consistency: not testable with zero qualified observations.
- MCX consistency: not testable because the corpus contains no MCX sample.
- LONG/SHORT consistency: not testable with zero qualified observations.
- Session phase: all considered observations are end-of-session boundaries;
  there is no phase-diverse eligible population.
- Small-threshold movement: not testable.
- Sample concentration: the evidence spans 93 subjects and five sessions, but
  that breadth cannot compensate for missing mandatory K5 facts and outcomes.

## Decision options for EA/Sponsor

No numeric candidate is evidence-supported by this corpus. The bounded options
are:

1. Keep `MATERIAL_EXTENSION_THRESHOLD = POLICY_UNRESOLVED` and K5
   `UNAVAILABLE`.
2. Separately govern an Intraday 15M structural-origin contract, an Intraday
   15M ATR period/calculation identity, and a factual forward-outcome contract;
   then reconstruct an exact no-look-ahead corpus and repeat this analysis.
3. If a future governed corpus remains family-imbalanced, commission additional
   retained evidence before deciding common versus family-specific policy.

## Conclusion

`K5_THRESHOLD_STILL_UNRESOLVED = YES`

`K5_COMMISSIONING_EVIDENCE_READY = NO`

The next step is an architecture/methodology work order for the three missing
fact contracts, followed by evidence reconstruction. No classifier, runtime,
Browser, production policy, or analytical state was changed.
