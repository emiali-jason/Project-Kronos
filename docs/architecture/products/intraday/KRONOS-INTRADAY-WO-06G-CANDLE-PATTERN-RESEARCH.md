# WO-06G — Candlestick and price-action research

Status: WO_06G_PASS = YES; research complete / publication review pending. Publication and activation are not authorized.
Authority: Sponsor WO-06G work order, live-shadow addendum and final pass contract.
Baseline: develop `8ffb28edb496f0fd48d5e5da589f51875b1a7ba0`.
This is an offline derived research projection, with no runtime composition or write-back seam.

## Governing inputs and reconciliation

- Published WO-06A methodology 2.2.0 and lawful 09:30 Opening remain unchanged.
- WO-06B exact subject/benchmark/previous-session binding remains unchanged.
- WO-06C Assessment Price/Time authority remains unchanged; no historical backfill.
- WO-06D includes every admission in the measurement denominator, independently of Review or trading selection.
- Published WO-06E retains 572 eligible observations, 33 baseline admissions, 107 no-CPR admissions, 74 CPR sole blockers, 329 CPR-plus-other blockers, zero removed admissions. Production Narrow CPR is unchanged.
- WO-06F is consumed as a sealed input, not recalculated. Its accepted research identity is `WO06F-RESEARCH-415176852e5b3e9e493af5db6259419babbea6b6fc7dac7c610d9cf04926ada3`.
- DOMAIN-001 native analytical subjects, expiry-specific contracts and reference context remain separate. Exact same-operation MCX history proof is required; no ticker inference or current-contract fallback.
- DOMAIN-008 governed calendar windows establish completion and session coverage. Session boundaries, including shortened terminal candles, are reused unchanged.
- Current Authority Manifest V1 and Living Master contain historical roadmap labels and historical snapshots. The current direct Sponsor WO-06E/F/G decisions and their published contracts control this work; no stale roadmap label is treated as new implementation authority.
- Masterclass document `1hQJD_rw605BVNDqXIhlZDkV7078RrYqZ0jtW9RBiX0M` was read as research input only. Its Hero/Bahubali discussion requires context and supplies no numerical wick/body or dominance threshold. It is not a production admission contract.
- Living Master `1o5sv4Yukldeqe32bRObgEorKl3PhUwhqV8ZwowpTxmU` was inspected read-only. Neither document was modified.

## Predeclared observation model

Definitions and table dimensions were recorded before pattern counts in the working evidence `WO-06G/predeclared.md`.
The primary observation is the last completed current-session candle at each exact historical boundary, with its immediately preceding completed candle where required.
5M, 15M and 1H remain separate. Prior-session 1H context remains lawful context, but is not silently concatenated into a current-session two-candle pattern.
All completed current-session candles receive deterministic geometry identities; only the last-candle geometry, preceding source identity and aggregate source-set identity are retained in the compact projection.
Earlier candles do not create additional admission observations. The raw denominator remains 882 subject/run records across nine runs, with 572 eligible and 310 unavailable.
A missing current 1H candle never delays Opening and never becomes a forming completed candle.

Each geometry record binds canonical subject; native contract and historical binding where applicable; timeframe; governed session; open/close time; historical observation boundary; source candle, integrity and operation; OHLC; meaningful raw volume; calculation version and geometry identity.
The policy is `WO06G-COMPLETED-CANDLE-GEOMETRY-V1`.
Source restoration/integrity and exact expected coverage are checked before geometry. Duplicate, out-of-order, incomplete, foreign-subject/session/timeframe/operation or future candles fail closed.

| Fact | Exact definition |
| --- | --- |
| Range | high − low |
| Body | abs(close − open) |
| Direction | BULLISH if close > open; BEARISH if close < open; FLAT otherwise |
| Upper wick | high − max(open, close) |
| Lower wick | min(open, close) − low |
| Body/wick ratios | corresponding length / range |
| Open/close location | (price − low) / range |
| Range expansion ratio | current range / immediately preceding range |
| Body expansion ratio | current body / immediately preceding body |
| Zero denominator | missing ratio, with explicit zero-range or predecessor geometry; never division by zero |
| Precision | Decimal precision 28, ROUND_HALF_EVEN, independent of caller context |

Candle prices are explicitly `CANDLE_GEOMETRY_NOT_ASSESSMENT_PRICE`.
NIFTY/BANKNIFTY volume remains unavailable as meaningful traded volume; no futures or equity proxy is substituted.

## Exact geometric classifications and deferred labels

- Body engulfing requires opposite, nonzero body directions, current body containment of previous body, and at least one strictly extended edge. Equal reversed bodies do not qualify. Bullish and bearish variants retain candle direction, never rewrite Probables direction.
- Full-range engulfing/outside bar means current high >= previous high and current low <= previous low, with at least one strict extension. These are the same mask and must not be counted twice.
- Inside bar is inclusive containment within the previous range with at least one strict contraction. Identical ranges have the separate EQUAL_RANGE state.
- EXPANSION means only current range > previous range. It does not mean an impulse, strength, breakout or a profitable opportunity.
- OPEN_EQUALS_CLOSE is exact equality, not an adopted Doji threshold.
- Hammer, hanging man, inverted hammer, shooting star, pin bar, long-wick rejection, Doji, spinning top, Marubozu/body dominance, multi-candle reversal, continuation and Hero/Bahubali binary labels are DEFER_BINARY_THRESHOLD. Continuous lengths/ratios remain available. There is no silent threshold, tolerance, parameter sweep or optimization.
- True breakout/breakdown, failed breakout, break-retest-hold/fail and liquidity-sweep authority remain NOT_ESTABLISHED without an exact cohort-bound governed barrier/event. A prior-candle high/low is not promoted to that authority.
- Future confirmation cannot be borrowed from candles after the observation boundary. No named reversal or continuation is retrospectively confirmed.

## Exact historical level context

Same-replay previous-session PDH, PDL, CPR lower, CPR upper and pivot are consumed from their sealed governed facts; CPR is not recalculated.
Their subject, target session, previous session, daily candle, OHLC, completion time and boundary must agree exactly. Levels must have been available before the measured candle began.
The source level identity is retained. Missing or ambiguous authority is not filled from legacy artifacts or later evidence.

INTERSECTS_LEVEL means low <= level <= high, including an exact touch. Entirely above/below are strict.
Raw close-minus-level distance is reported without a NEAR threshold or trading interpretation.
Breach-below/reclaim is low < level and close > level; breach-above/return is high > level and close < level.
These are within-candle price geometries, not inferred liquidity sweeps, breakouts or retests. Boundary equality alone does not satisfy a strict breach/reclaim.
An incomplete level set with no observed event remains unknown; absence is established only against the complete five-level set.

## Context reuse and tables

WO-06F SMA20/50, VWAP, volume, local 15M structure, NIFTY relationship and published participation records retain their original values, source bindings and timestamps. No new indicator calculation occurs.
Primary predeclared cross tables are pattern × phase, direction, subject type, cohort, Narrow CPR, 5M SMA20 side, 5M SMA50 side, 5M VWAP side and 5M volume-normalization availability.
The 5M context dimension stays explicitly named when compared with a 15M or 1H candle; it is not relabelled as an indicator on that other timeframe.
Each timeframe/family reports eligible denominator, evaluated, unavailable, present and absent. Deferred labels have zero evaluated, not zero prevalence.
Continuous distributions report min/median/max and missing counts. Absolute price-unit distributions across unlike securities are descriptive inventories, not comparable economic effect sizes; subject-type strata and dimensionless ratios are also supplied.
CPR direction, band relationship, Virgin CPR and multi-day Narrow remain NOT_ESTABLISHED where the retained preceding context is incomplete, as accepted in WO-06E.
SMA200 and strict stack remain NOT_ESTABLISHED. Published participation is not replaced by raw volume.

## Dependence and interpretation

Repeated subject/session observations are not independent trades. Report raw observations and distinct subject/session groups separately.
Sensitivity weights each observation by 1 / eligible observations in its subject/session group. Report exact Fraction weighted-present and weighted-evaluable totals, not an invented effective trade sample.
The 107 counterfactual observations remain the WO-06E population with its previously proposed 105 episodes; WO-06G does not redefine those episodes.
Baseline and CPR-sole-blocked cohorts are compared descriptively with the same fields. Neither selection nor missing feature availability changes the denominator.
Full-range engulfing is definitionally redundant with outside-bar status. Bullish/bearish variants partition a parent mask; inside/outside/equal are mutually exclusive. They do not add independent confirmations.
All pairwise overlaps are measured per timeframe. Indicator/pattern vote counts, confluence scores and ranking are rejected.
Predictive value, win rate, profitability, missed winners/trades/profits, MFE and MAE are NOT_ESTABLISHED. The 33 historical admissions retain PRICE_NOT_RETAINED. No candle close, later LTP, chart, Review, Answer, entry or broker price is substituted.

## Feature disposition and minimum prospective recommendation

| Feature | Disposition | Reason |
| --- | --- | --- |
| Existing Narrow CPR | EXISTING_PRODUCTION_AUTHORITY | unchanged admission rule; predictive value unresolved |
| 5M SMA20/50 side where available | LIVE_SHADOW_CANDIDATE | unchanged WO-06F recommendation; non-blocking context |
| 5M research VWAP side | LIVE_SHADOW_CANDIDATE | unchanged completed-session typical-price formula; no index proxy |
| 5M/15M body ratio, upper/lower wick ratios, close location | LIVE_SHADOW_CANDIDATE | small deterministic geometry vector; no named threshold |
| 5M/15M range ratio and pair-range state | LIVE_SHADOW_CANDIDATE | directly reproducible; retain INSIDE/OUTSIDE/EQUAL/OTHER/UNAVAILABLE once |
| Body direction and exact body engulfing | RESEARCH_ONLY | derivable from geometry; does not establish takeover effectiveness |
| 1H geometry | RESEARCH_ONLY | availability is phase-dependent; not an Opening prerequisite |
| Exact PDH/PDL/CPR intersections and breach/reclaim | RESEARCH_ONLY | bounded price geometry; no proven breakout consequence |
| Absolute body/wick/range lengths, open location | CONTINUOUS_FACT_ONLY | retain detailed temporary geometry, avoid duplicating permanent fields |
| SMA slopes, VWAP slope/distance, volume normalization | RESEARCH_ONLY | preserve WO-06F limits; no new production filter |
| Hammer/Doji/spinning top/Marubozu and similar named labels | SPONSOR_DECISION_REQUIRED / DEFER_BINARY_THRESHOLD | no governed numerical definition; not needed for continuous capture |
| Hero/Bahubali and meaningful consolidation | VISUAL_HANDOVER_TO_WO07 | quantitative components available; visual/context sufficiency unresolved |
| True break/retest/failure and liquidity sweep | NOT_ESTABLISHED | exact barrier/event authority absent |
| SMA200, strict stack | NOT_ESTABLISHED | historical lookback missing |
| Outside plus full-range engulfing as two votes | REJECTED_AS_REDUNDANT | identical masks |
| Pattern/indicator voting, confluence score | REJECTED_AS_REDUNDANT | correlated descriptions do not create independent evidence |

WO-06H should select the minimum set, not automatically activate every recommendation above.
No live-shadow field is a gate, score, direction override or new candidate-selection rule.
Missing measurements remain represented; no observation is dropped because one feature is unavailable.

## Same-schema prospective cohorts and shadow price authority

Design only: no collector, runtime hook, persistence or monthly workbook is implemented here.
Cohort A = every production admission. Cohort B = exact CPR sole-blocked research observation under the unchanged all-other-requirements counterfactual.
Cohort B cannot become a Probable, Review, Promotion, Risk, Entry, PAPER/LIVE or broker candidate.

Common compact schema for A and B:

- research observation ID, cohort, source run/result/mapping, canonical subject, native contract/binding when applicable;
- phase, direction, methodology and research-definition versions, analysis boundary, governed session;
- baseline state, Narrow CPR fact/availability, denominator membership and proposed dependence/episode key;
- Assessment authority classification, observed price and its quote timestamp, exact subject/source observation and integrity identity, missing reason;
- capture operation/request identity and receipt timestamp separately from quote time;
- 5M SMA20/50 side and availability, 5M research VWAP side/availability with retained source/boundary identities;
- for each selected 5M/15M candle: source/close timestamp, body and wick ratios, close location, range ratio, pair-range state and availability;
- monthly cohort completeness/reconciliation identity; outcome state initially NOT_ESTABLISHED, with future outcome authority/version/source links only when genuinely available.

SHADOW_ASSESSMENT_AUTHORITY_REQUIRED = YES.
WO-06C covers admitted opportunities. It does not automatically authorize a price request for a CPR-blocked non-admission.
WO-06H must obtain separate bounded research-only authority for the exact native analytical subject, same Provider observation price/time, prospective operation timing and request accounting before Cohort B capture.
Capture must follow the completed baseline/counterfactual decision and precede research-row publication. Request receipt time is not Assessment Time. Failure yields PRICE_NOT_RETAINED without deleting a row or altering admission.
No historical reconstruction and no later quote, candle close or chart fallback is allowed. The same schema carries different truthful authority classifications for A and B.

EOD/outcome measurement needs separately accepted observation, price, timestamp, session-end, direction, corporate-action/contract-roll, missing-data, integrity and reconciliation rules. Those rules cannot be inferred from candle-pattern prevalence.
The initial one-month window is approved direction only; exact start/end, activation and integrated tests belong to WO-06H. Month-end review does not automatically promote any feature to production.

## Monthly working record and retention

Compact prospective rows must support a later monthly opportunity ledger with all A/B observations, availability, source references, denominator reconciliation and integrity checks.
Permanent artifacts: final monthly Excel; GitHub source/tests/governance; Living Master/programme governance.
Temporary artifacts: operational/analytical/research working evidence, including these detailed geometry projections.
Retention: current month plus five calendar days. Purge only after the previous monthly Excel is finalized, reconciled and integrity verified.
This candidate implements neither Excel nor purge. It does not create an unnecessary permanent raw candle archive or delete any current evidence.

## WO-07 visual handover — current Q1–Q10 unchanged

| Concept | Why geometry is insufficient | Required chart evidence/timeframes | OBSERVABLE / AMBIGUOUS / NOT_OBSERVABLE | Machine facts accompanying |
| --- | --- | --- | --- | --- |
| Meaningful consolidation | duration, location and visual structure lack a governed exact barrier here | labelled native chart with time axis; 15M and 5M lead-in, 1H only completed context | clearly bounded lead-in / competing ranges / cropped or unreadable lead-in | exact candle times, range/body ratios, source-bound level facts |
| Hero/Bahubali candidate context | a large body alone does not prove escape, acceptance or exhaustion | completed 15M/5M candidate and preceding context, volume if meaningful | context and completed candle visible / conflicting interpretations / necessary panels absent | body/wick/range ratios, raw/normalized volume availability, no automatic Hero label |
| Break/retest narrative | true barrier identity and chronological event authority are missing | labelled barrier and completed breakout/retest candles on 15M/5M | sequence and level visible / uncertain barrier or chronology / no level or confirmation in view | machine barrier availability and timestamps; unavailable remains unavailable |
| Rejection or failed follow-through | wick geometry alone does not establish rejection meaning | native 5M/15M level interaction and completed follow-through at the permitted boundary | clear interaction / overlapping explanations / cropped or future-only confirmation | exact wick ratios and source-bound level-intersection geometry |
| Multi-candle reversal/continuation | geometric sequence lacks agreed pattern definition and contextual sufficiency | complete 5M/15M sequence with surrounding native context | complete readable sequence / unclear context / missing candles | body directions, exact OHLC relationships, declared missing authority |
| Native/reference and panel readability | visual series/panels must be independently observed | exact symbol/contract, exchange, timeframe, price/time axes; MCX native/reference distinct | readable exact identity / ambiguous text / absent identity | governed subject/native binding and required panel contract |

Analyst reports visible observations and uncertainty only; no internal hash validation, numerical reconstruction, contract inference, admission decision or trading consequence is delegated to it.
Machine owns arithmetic, source integrity, time/session binding and authority enforcement. A visual observation cannot fill missing governed machine authority.
This is a handover proposal, not a Chart Analyst contract or Browser change.

## WO-08 and WO-06H boundaries

WO-08 remains reserved for the Sponsor TradingView/Astra successor. Recommendations only: readable exact native identity/exchange, explicit timeframe and time axes, completed-versus-forming distinction, enough contextual lead-in, meaningful volume panels where applicable, and separate MCX reference row. No Pine, chart upload, screenshot requirement, new visual contract or successor implementation is introduced.

WO_06H_INTEGRATION_HANDOVER:

1. Integrate accepted WO-06E CPR impact and unresolved predictive value with unchanged WO-06F technical facts and this WO-06G geometry.
2. Select and authorize the minimum one-month shadow feature set and exact observation window.
3. Keep existing production Narrow CPR authoritative; no automatic methodology promotion.
4. Explicitly authorize Cohort B and its separate same-observation Assessment Price/Time capture before any Provider request.
5. Implement only approved research persistence, immutable identity, missing-data states, all-member denominator and restoration/replay behavior.
6. Reconcile monthly-working-ledger and future outcome authorities without prematurely implementing monthly Excel or purge.
7. Qualify A/B same-schema capture, baseline independence, failure without admission change, request accounting, source/session/contract checks, 09:30 behavior, restart restoration, idempotency and partial-failure retention.
8. Prove zero Review/trading/broker authority from shadow rows and preserve WO-07/08/09 sequence.
9. Review availability, dependence, phase/direction/cohort comparisons and exact outcome authority before any later policy proposal.
10. Close WO-06 only after its separately authorized integrated gates pass. WO-06H is NOT STARTED by this candidate.

## Historical results

Research identity: `WO06G-RESEARCH-ab3c4f33ce7f2c5665b5a5a1de12dcf1605863734db5dceadb87ea9abd1e2515`. Independent rerun: identical.

| Timeframe | Eligible | Geometry available | Geometry unavailable | Completed source candles | Latest zero-range |
| --- | ---: | ---: | ---: | ---: | ---: |
| 5M | 572 | 572 | 0 | 28808 | 1 |
| 15M | 572 | 572 | 0 | 9474 | 0 |
| 1H | 572 | 478 | 94 | 2228 | 0 |

The 310 ineligible source rows remain outside each 572-row pattern denominator and are retained explicitly.

| Family / mask | 5M evaluated / present / absent / unavailable | 15M evaluated / present / absent / unavailable | 1H evaluated / present / absent / unavailable |
| --- | --- | --- | --- |
| BEARISH_BODY_ENGULFING | 572 / 45 / 527 / 0 | 485 / 51 / 434 / 87 | 478 / 29 / 449 / 94 |
| BEARISH_FULL_RANGE_ENGULFING | 572 / 56 / 516 / 0 | 485 / 38 / 447 / 87 | 478 / 29 / 449 / 94 |
| BODY_DOMINANCE | 0 / 0 / 0 / 572 | 0 / 0 / 0 / 572 | 0 / 0 / 0 / 572 |
| BODY_ENGULFING | 572 / 110 / 462 / 0 | 485 / 129 / 356 / 87 | 478 / 67 / 411 / 94 |
| BREAK_RETEST | 0 / 0 / 0 / 572 | 0 / 0 / 0 / 572 | 0 / 0 / 0 / 572 |
| BULLISH_BODY_ENGULFING | 572 / 65 / 507 / 0 | 485 / 78 / 407 / 87 | 478 / 38 / 440 / 94 |
| BULLISH_FULL_RANGE_ENGULFING | 572 / 79 / 493 / 0 | 485 / 78 / 407 / 87 | 478 / 40 / 438 / 94 |
| CONTINUATION | 0 / 0 / 0 / 572 | 0 / 0 / 0 / 572 | 0 / 0 / 0 / 572 |
| EQUAL_RANGE | 572 / 5 / 567 / 0 | 485 / 2 / 483 / 87 | 478 / 0 / 478 / 94 |
| EXPANSION | 572 / 328 / 244 / 0 | 485 / 312 / 173 / 87 | 478 / 250 / 228 / 94 |
| FAILED_BREAK | 0 / 0 / 0 / 572 | 0 / 0 / 0 / 572 | 0 / 0 / 0 / 572 |
| FULL_RANGE_ENGULFING | 572 / 139 / 433 / 0 | 485 / 119 / 366 / 87 | 478 / 69 / 409 / 94 |
| HERO_BAHUBALI | 0 / 0 / 0 / 572 | 0 / 0 / 0 / 572 | 0 / 0 / 0 / 572 |
| INDECISION_GEOMETRY | 0 / 0 / 0 / 572 | 0 / 0 / 0 / 572 | 0 / 0 / 0 / 572 |
| INSIDE_BAR | 572 / 76 / 496 / 0 | 485 / 61 / 424 / 87 | 478 / 106 / 372 / 94 |
| LEVEL_BREACH_RECLAIM | 572 / 162 / 410 / 0 | 572 / 265 / 307 / 0 | 478 / 256 / 222 / 94 |
| MULTI_CANDLE_REVERSAL | 0 / 0 / 0 / 572 | 0 / 0 / 0 / 572 | 0 / 0 / 0 / 572 |
| OPEN_EQUALS_CLOSE | 572 / 26 / 546 / 0 | 572 / 10 / 562 / 0 | 478 / 6 / 472 / 94 |
| OUTSIDE_BAR | 572 / 139 / 433 / 0 | 485 / 119 / 366 / 87 | 478 / 69 / 409 / 94 |
| REJECTION | 0 / 0 / 0 / 572 | 0 / 0 / 0 / 572 | 0 / 0 / 0 / 572 |

### Continuous geometry distributions

Cells are available count; min / median / max. Missing ratios are not zeros.

| Fact | 5M | 15M | 1H |
| --- | --- | --- | --- |
| body | 572; 0.0 / 1.0 / 834.0 | 572; 0.0 / 1.7 / 934.0 | 478; 0.0 / 2.2 / 4759.0 |
| body_expansion_ratio | 551; 0 / 1 / 115 | 470; 0 / 1.445175438596491228070175439 / 159 | 473; 0 / 0.9065420560747663551401869159 / 43.5 |
| body_ratio | 571; 0 / 0.4444444444444444444444444444 / 1 | 572; 0E+1 / 0.4330305147915210808292569298 / 1 | 478; 0E+1 / 0.4309018567639257294429708223 / 1 |
| close_location | 571; 0 / 0.6 / 1 | 572; 0 / 0.579473684210526315789473684 / 1 | 478; 0 / 0.5603864734299516908212560385 / 1 |
| lower_wick | 572; 0.0 / 0.4 / 511.0 | 572; 0.0 / 1.1 / 340.0 | 478; 0.0 / 1.17 / 1922.0 |
| lower_wick_ratio | 571; 0 / 0.2307692307692307692307692308 / 1 | 572; 0 / 0.2903767251025736665423349496 / 0.95 | 478; 0 / 0.2364766081871345029239766082 / 0.8837209302325581395348837209 |
| open_location | 571; 0 / 0.4032258064516129032258064516 / 1 | 572; 0 / 0.5359718406593406593406593405 / 1 | 478; 0 / 0.4588963963963963963963963964 / 1 |
| range | 572; 0.0 / 2.775 / 1015.0 | 572; 0.03 / 4.8 / 1015.0 | 478; 0.06 / 7.75 / 6681.0 |
| range_ratio | 565; 0.1666666666666666666666666667 / 1.181818181818181818181818182 / 19 | 484; 0.09051724137931034482758620690 / 1.356818181818181818181818182 / 11.4 | 477; 0.1347517730496453900709219858 / 1.055118110236220472440944882 / 5.789428076256499133448873484 |
| upper_wick | 572; 0.0 / 0.4 / 134.0 | 572; 0.0 / 0.5 / 277.0 | 478; 0.0 / 1.5 / 666.0 |
| upper_wick_ratio | 571; 0 / 0.2105263157894736842105263158 / 1 | 572; 0 / 0.1929818928984204443302940798 / 0.9230769230769230769230769231 | 478; 0 / 0.2537787513691128148959474260 / 0.9292035398230088495575221239 |

### Identical cohort fields

Cells are present / evaluated, not predictive success.

| Cohort | Raw observations | TF | Body engulf | Outside | Inside | Expansion | Level breach/reclaim |
| --- | ---: | --- | --- | --- | --- | --- | --- |
| baseline | 33 | 5M | 6 / 33 | 8 / 33 | 2 / 33 | 21 / 33 | 8 / 33 |
| baseline | 33 | 15M | 9 / 31 | 0 / 31 | 0 / 31 | 24 / 31 | 15 / 33 |
| baseline | 33 | 1H | 6 / 30 | 0 / 30 | 0 / 30 | 24 / 30 | 21 / 30 |
| sole_blockers | 74 | 5M | 11 / 74 | 16 / 74 | 3 / 74 | 45 / 74 | 17 / 74 |
| sole_blockers | 74 | 15M | 17 / 65 | 0 / 65 | 0 / 65 | 48 / 65 | 32 / 74 |
| sole_blockers | 74 | 1H | 11 / 65 | 0 / 65 | 0 / 65 | 46 / 65 | 36 / 65 |
| no_cpr | 107 | 5M | 17 / 107 | 24 / 107 | 5 / 107 | 66 / 107 | 25 / 107 |
| no_cpr | 107 | 15M | 26 / 96 | 0 / 96 | 0 / 96 | 72 / 96 | 47 / 107 |
| no_cpr | 107 | 1H | 17 / 95 | 0 / 95 | 0 / 95 | 70 / 95 | 57 / 95 |

### Phase, direction and instrument strata

All dimensions have complete per-family, per-timeframe evaluated/unavailable/present/absent and continuous distributions in the compact research projection. The following readable view shows 5M pattern counts.

| Dimension | Value | Eligible | Body engulf present/evaluated | Outside present/evaluated | Expansion present/evaluated |
| --- | --- | ---: | --- | --- | --- |
| phase | CURRENT_SESSION_ESTABLISHED | 478 | 94/478 | 135/478 | 304/478 |
| phase | OPENING | 87 | 15/87 | 4/87 | 21/87 |
| phase | STRUCTURE | 7 | 1/7 | 0/7 | 3/7 |
| direction | CONFLICTING | 34 | 9/34 | 8/34 | 19/34 |
| direction | LONG | 79 | 11/79 | 12/79 | 37/79 |
| direction | NON_DIRECTIONAL | 355 | 69/355 | 103/355 | 223/355 |
| direction | SHORT | 104 | 21/104 | 16/104 | 49/104 |
| subject_type | BANKNIFTY | 6 | 0/6 | 3/6 | 3/6 |
| subject_type | MCX | 20 | 6/20 | 2/20 | 6/20 |
| subject_type | NIFTY | 6 | 0/6 | 3/6 | 4/6 |
| subject_type | NSE_EQUITY | 540 | 104/540 | 131/540 | 315/540 |
| narrow | False | 403 | 80/403 | 96/403 | 227/403 |
| narrow | True | 169 | 30/169 | 43/169 | 101/169 |
| sma20_5m | ABOVE | 244 | 43/244 | 66/244 | 153/244 |
| sma20_5m | BELOW | 234 | 51/234 | 69/234 | 151/234 |
| sma20_5m | NOT_ESTABLISHED | 94 | 16/94 | 4/94 | 24/94 |
| sma50_5m | ABOVE | 127 | 20/127 | 48/127 | 103/127 |
| sma50_5m | BELOW | 160 | 38/160 | 62/160 | 133/160 |
| sma50_5m | NOT_ESTABLISHED | 285 | 52/285 | 29/285 | 92/285 |
| vwap_5m | ABOVE | 254 | 50/254 | 60/254 | 141/254 |
| vwap_5m | BELOW | 306 | 60/306 | 73/306 | 180/306 |
| vwap_5m | NOT_ESTABLISHED | 12 | 0/12 | 6/12 | 7/12 |
| volume_5m | AVAILABLE | 467 | 94/467 | 129/467 | 298/467 |
| volume_5m | INSUFFICIENT_POSITIVE_PRIOR_20 | 93 | 16/93 | 4/93 | 23/93 |
| volume_5m | NOT_ESTABLISHED | 12 | 0/12 | 6/12 | 7/12 |

MCX: COPPER 5, CRUDE 6, GOLDM 4, SILVERM 5; NATGAS has no eligible historical observation. No fixture or current contract is inserted to fill this absence. NSE equities 540; NIFTY 6; BANKNIFTY 6; MCX 20.

### Overlap and dependence

| Pair | 5M both present | 15M both present | 1H both present |
| --- | ---: | ---: | ---: |
| FULL_RANGE_ENGULFING / OUTSIDE_BAR | 139 | 119 | 69 |
| BODY_ENGULFING / OUTSIDE_BAR | 55 | 57 | 15 |
| BODY_ENGULFING / EXPANSION | 92 | 106 | 54 |
| OUTSIDE_BAR / EXPANSION | 139 | 119 | 69 |
| INSIDE_BAR / OUTSIDE_BAR | 0 | 0 | 0 |

572 eligible observations represent 473 subject/session groups. Weighted totals below assign each group total weight one; they do not establish independent outcomes.

| TF | Pattern | Weighted present | Weighted evaluated |
| --- | --- | --- | --- |
| 5M | BODY_ENGULFING | 88 | 473 |
| 5M | OUTSIDE_BAR | 683/6 | 473 |
| 5M | INSIDE_BAR | 178/3 | 473 |
| 5M | EXPANSION | 549/2 | 473 |
| 5M | LEVEL_BREACH_RECLAIM | 133 | 473 |
| 15M | BODY_ENGULFING | 283/3 | 386 |
| 15M | OUTSIDE_BAR | 286/3 | 386 |
| 15M | INSIDE_BAR | 146/3 | 386 |
| 15M | EXPANSION | 1499/6 | 386 |
| 15M | LEVEL_BREACH_RECLAIM | 1331/6 | 473 |
| 1H | BODY_ENGULFING | 178/3 | 381 |
| 1H | OUTSIDE_BAR | 181/3 | 381 |
| 1H | INSIDE_BAR | 76 | 381 |
| 1H | EXPANSION | 646/3 | 381 |
| 1H | LEVEL_BREACH_RECLAIM | 587/3 | 381 |

Observed prevalence varies across phase, direction and selected cohorts. This is a conditional descriptive result, not evidence of incremental return. Production admission already conditions several price relationships; the absence of inside/outside bars in the 15M selected cohorts is not an independently discovered trading edge.

## Qualification and publication boundary

Focused: 71/71 PASS. Affected: 1,173/1,173 PASS (126.36 seconds). Complete active repository: 6,422/6,422 PASS (1,104.32 seconds). Source/test bytes were unchanged through full regression. Syntax/in-memory compile PASS; diff whitespace checks PASS; changed-scope secret scan zero findings. Offline replay reproduced the identical research identity; all 882 upstream rows and 1,716 timeframe windows passed the preservation audit.

No existing production source file is modified. Four new Intraday-owned paths only: pure geometry, offline read adapter, focused tests, this document. No Browser, Chart Analyst, Pine, Swing or shared-source change. No stage, commit or push. No runtime restart, Refresh, Provider/OpenAI/broker operation or production evidence write is initiated by WO-06G. Final preservation inventory and exact hashes accompany the candidate evidence pack.

## Threshold decision register

| Concept | Continuous alternative | Binary disposition | Needed for WO-06G PASS? |
| --- | --- | --- | --- |
| Doji/spinning top | body/range and both wick/range ratios | DEFER_BINARY_THRESHOLD to prospective research | NO; continuous facts suffice |
| Hammer/pin/rejection/shooting star | wick/body geometry and exact source-bound level interaction | DEFER_BINARY_THRESHOLD to prospective research | NO; continuous facts suffice |
| Marubozu/body dominance | body/range, close location and wick ratios | DEFER_BINARY_THRESHOLD to prospective research | NO; continuous facts suffice |
| Meaningful expansion/impulse | range ratio; exact increase alone is not an impulse threshold | DEFER_BINARY_THRESHOLD to prospective research | NO; continuous facts suffice |
| Hero/Bahubali | range/body/wick/volume components; meaningful consolidation remains visual/unestablished | DEFER_BINARY_THRESHOLD to prospective research | NO; continuous facts suffice |
| Volume expansion | unchanged WO-06F raw change and normalized ratio where available | DEFER_BINARY_THRESHOLD to prospective research | NO; continuous facts suffice |
| Multi-candle reversal/continuation | ordered completed body directions and exact pair geometry; contextual rule not established | DEFER_BINARY_THRESHOLD to prospective research | NO; continuous facts suffice |

No numerical label threshold is recommended from the historical counts. If a later binary label is desired, Sponsor definition and prospective validation are required; no outcome optimization is permitted.

### Unchanged volume-change relationship cross table

| Volume change | Eligible | 5M body engulf | 5M outside | 5M expansion | 5M level breach/reclaim |
| --- | ---: | ---: | ---: | ---: | ---: |
| ABOVE | 342 | 78 | 114 | 254 | 100 |
| AT | 1 | 0 | 0 | 0 | 0 |
| BELOW | 217 | 32 | 19 | 67 | 56 |
| NOT_ESTABLISHED | 12 | 0 | 6 | 7 | 6 |

These are comparisons with retained WO-06F volume changes, not new participation or volume-expansion policy. Full per-timeframe/family availability tables are retained in `volume-relationship.json` as temporary working research evidence.

## Final production preservation and stop

75,028/75,028 baseline files remain byte-identical; modified 0, missing 0. Four concurrent Swing monitoring additions are preserved (after inventory 75,032): two CAPABILITY_UNAVAILABLE and two PROVIDER_CAPABILITY_NOT_ACTIVE interruption records. Initiating actor/cause NOT_ESTABLISHED; no attribution to WO-06G. Carry this observation to deferred shared/Swing hardening without implementing it here.

Runtime PID 21692 remained present. WO-06G initiated Provider/OpenAI/broker operations, Refreshes and restarts: 0. No historical Assessment backfill or live observation publication. No stage, commit or push. WO-06H/07/09 not started; WO-08 reserved. Statistics/monthly Excel and WO-10 revalidation held; purge not implemented; WO-18 held. Genuine WO-06G candidate blocker: NONE.
