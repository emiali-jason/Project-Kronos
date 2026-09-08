# WO-06F — Offline technical-context research

Status: Proposed engineering/research candidate; Sponsor publication review pending.
Date: 2026-09-08. Production authority: NONE.

## Authority and boundaries

The Sponsor's WO-06F instruction, prospective-field addendum and 85-item return
contract authorize this bounded research. The subsequent explicit VWAP decision
selects `sum(((H+L+C)/3)*V)/sum(V)`. This document records that research decision;
it does not amend the production methodology. WO-06H owns later feature disposition.

Published prerequisite: `997e3902c05eee57f74fe24874f4baf01597e2d6`.
Production methodology remains 2.2.0. WO-06A Opening, WO-06B source binding,
WO-06C Assessment observation authority and WO-06D population authority are unchanged.
The nine historical runs retain their original 2.0.0/2.1.0 decisions; they are not
reinterpreted under 2.2.0. The earlier Living Master programme labels are not a
new authority to execute other slices: the current Sponsor WO-06 sequence governs.

References: the Intraday product authority documents and Current Authority Manifest;
WO-06D population measurement; WO-06E CPR incremental-value research; DOMAIN-001
completed evidence; DOMAIN-008 explicit sessions; existing `wo10_facts.py` arithmetic
and `historical_semantic.py` / `structure.py` factual policies. Reusing their pure
arithmetic here does not invoke WO-10 or confer classification/trading authority.
The Sponsor masterclass is a hypothesis source, not empirical validation:
[provided masterclass](https://docs.google.com/document/d/1hQJD_rw605BVNDqXIhlZDkV7078RrYqZ0jtW9RBiX0M/edit).

## Fixed population and CPR input

The adapter takes the original WO-06E projection as a read-only input. It verifies
its content digest and the exact accepted identity, then joins source result,
run, mapping, boundary and Narrow CPR identity to recursively validated retained
Probables/replay artifacts. It does not rerun the CPR counterfactual.

Accepted input:
`WO06E-RESEARCH-1d118f57ed95cc58a4d304e97a635ed1dc72cad5f6262a90d6bd7eddb314b015`.

| Population/result | Count |
| --- | ---: |
| Runs | 9 |
| Subject/run observations | 882 |
| Evaluable / unavailable | 572 / 310 |
| Baseline / without-CPR admissions | 33 / 107 |
| CPR sole blockers / CPR plus other blockers | 74 / 329 |
| Admissions removed | 0 |
| Narrow / non-Narrow eligible observations | 169 / 403 |

All 882 rows remain represented; unavailable rows do not become admissions.
The 572 eligible rows have 473 distinct subject/session groups, not 572 independent
trades. WO-06D's proposed episode projection remains 33 baseline and 105 no-CPR
episodes from 107 no-CPR admissions. Neither grouping establishes independence.
Repeated subjects, shared dates, common NIFTY context and phase/version composition
confound pooled comparisons. No uncertainty interval treating rows as independent
trades is appropriate here. All 33 historical admissions retain missing Assessment
Price; no reconstruction or historical write occurs.

## Exact measurement definitions

Each candle set verifies full supplied coverage against the exact DOMAIN-008
schedule, ordered unique completed intervals through the historical boundary,
subject, timeframe, session, acquisition operation and original integrity.
The report carries source fact/mapping identities and ordered candle-set digests;
retained source facts supply the exact constituent candle identities during retention.
Gaps, duplicates, mixed identities, out-of-order or future bars fail closed.

SMA uses existing simple-average arithmetic over completed closes for periods
20/50/200. Slope is current SMA minus SMA five completed bars earlier; its sign
has no tolerance or tuned threshold. `ABOVE/BELOW/AT` slope means positive/negative/
exact zero. At least period+5 closes are required. The strict research stack is
`last completed close > SMA20 > SMA50 > SMA200`, or its strict reverse. Equality
is mixed, not directional. This price is explicitly a completed-close research
input, NEVER an Assessment Price. The report retains that close's actual time.

Timeframes are separate: 1D uses the retained previous Daily candle; 1H uses the
exact governed previous and current sessions in chronological order; 15M and 5M
use the retained current session. The adapter does not extend lookback from unrelated
runs or silently mix intervals. No SMA200 proxy is permitted.

VWAP is research-only typical-price completed-5M session VWAP. Start from the
applicable governed session open; reset each session. Sum `(H+L+C)/3 * volume`
and divide by summed volume. No future/forming candle, previous-session accumulator,
tick-VWAP equivalence or missing opening segment is allowed. Individual known zero
volumes contribute zero weight; zero total volume is unavailable. Missing volume is
not converted to zero. NIFTY/BANKNIFTY meaningful traded volume is not established;
no index-futures/options volume is substituted.

VWAP slope is the exact difference between adjacent completed-5M cumulative values,
with no slope-strength threshold. Distance is completed 5M close minus VWAP;
percentage distance is that difference divided by VWAP times 100. Zero denominator
remains unavailable. All Decimal research arithmetic uses precision 28, half-even,
independent of caller context. These are descriptive research definitions only.

MCX calculations require matching retained native candles from the SAME acquisition
operation, canonical subject, exact intervals, boundary, session and OHLCV. Exact
contract and historical-binding identity must remain constant within the series.
Ambiguity/mismatch rejects; absent lineage or a contract transition remains unavailable.
No current-contract fallback, reference-series substitution, back-adjustment or
inferred roll lineage is used. All 20 eligible historical MCX rows satisfy this
join in the inspected cohort. NATGAS has no eligible row; it is not manufactured.

## Historical availability and measurements

| Timeframe | SMA20 | SMA50 | SMA200 | SMA20 slope | SMA50 slope |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1D | 0 | 0 | 0 | 0 | 0 |
| 1H | 8 | 0 | 0 | 4 | 0 |
| 15M | 287 | 0 | 0 | 14 | 0 |
| 5M | 478 | 287 | 0 | 478 | 287 |

Every strict three-SMA stack is NOT_ESTABLISHED because SMA200 history is missing.
5M price/SMA20: above 244, below 234, unavailable 94. SMA20 slope: rising 244,
falling 232, exact-flat 2, unavailable 94. 5M price/SMA50: above 127, below 160,
unavailable 285; slope rising 100, falling 187, unavailable 285.

VWAP is available for 560 rows: 540 NSE-equity and 20 native MCX. The 6 NIFTY and
6 BANKNIFTY observations remain unavailable. Completed close is above VWAP on 254
and below on 306. VWAP slope rises on 244, falls on 315 and is exactly flat on 1.
Distance percentages across the 560 rows range from -1.7740047061% to 1.6490661860%,
with median -0.04653214945%. These are distances, not returns or trading outcomes.

The existing published participation classification remains UNAVAILABLE for all
572 eligible rows (666 mappings across the whole population). Separately labelled
raw 5M volume is available on 560. Existing immediate-prior comparison and prior
20 positive-volume mean normalization are descriptive only: normalization is
available on 467; 93 have insufficient positive prior history; 12 lack meaningful
index volume. Volume is not liquidity, open interest or proof of strong participation.

Exact immediate-neighbour 15M H/L/C movement gives LONG 103, SHORT 131,
NON_DIRECTIONAL 251 and insufficient pair history 87. Original mapped phase facts
are preserved separately. This is local geometry, not a higher-level trend verdict.
No exact cohort-linked structural-barrier event or explicit range artifact establishes
break, breakdown, retest, return-through or consolidation. Each remains NOT_ESTABLISHED
on all 572 eligible rows, rather than false or invented. The 32 retained legacy structural artifacts date to 18–21 August and have
foreign legacy run identities; none belongs to this fixed cohort. They are not
borrowed as missing current-run events. Existing structural machinery
requires exact barriers/ranges; arbitrary automatic range or quality thresholds are
not introduced. Those unmodified mechanisms are covered by the repository regression.

## Predeclared comparisons and interpretation

Bounded comparisons: Narrow width x 5M SMA20 side; Narrow width x VWAP side;
5M SMA20/VWAP and SMA50/VWAP side agreement; Narrow width x 5M SMA20 side x 15M
local movement; 15M local movement x 5M immediate volume change; original NIFTY
relationship x 5M SMA20/VWAP side. Timeframes and predicates stay explicit.
No feature subsets, fitted score, threshold sweep or winner-selected tuning is used.
CPR direction/relationship/Virgin/multi-day confluences remain NOT_ESTABLISHED,
consistent with WO-06E's single-Daily historical limitation.

SMA20/VWAP: agree 366, conflict 102, unavailable pairing 104. SMA50/VWAP: agree 243,
conflict 38, unavailable pairing 291. Such agreement is correlated price context,
not independent confirmation. Preserve conflicts without adjudicating a new direction.

Narrow rows have SMA20 above/below/unavailable 77/73/19 and VWAP above/below/unavailable
82/82/5. Non-Narrow rows have SMA20 167/161/75 and VWAP 172/224/7. Width is not a
directional vote. Full directional CPR context cannot be inferred from these bins.

Baseline 33: SMA20 above/below/unavailable 13/17/3; VWAP 15/18/0; SMA20/VWAP
agree/conflict/unavailable 29/1/3. Sole-blocker 74: SMA20 32/33/9; VWAP 33/37/4;
SMA20/VWAP 59/2/13. These are selected cohorts with strong existing directional
constraints, not evidence that excluded candidates would be profitable.

The 87 Opening observations have insufficient current-session SMA20 history;
this must not delay the lawful 09:30 Opening assessment. The 7 Structure-phase
observations and 478 Established observations are separately reported. Baseline
Opening/Structure/Established counts remain 2/1/30; sole blockers 9/0/65.
All original LONG/SHORT and NIFTY facts remain untouched. Original Opening NIFTY
relationships are Supporting 81, Conflicting 5 and Not Applicable 1; missing
non-Opening relationships are not converted into neutral/supporting values.

Incremental-information disposition:
- Existing local movement, phase and NIFTY facts: ALREADY_ENCODED_BY_EXISTING_METHODOLOGY.
- SMA20/50 and VWAP side/slope/distance: POTENTIALLY_INCREMENTAL descriptive context;
  observed disagreements demonstrate different facts, not independent predictive value.
- Raw volume change/normalization: POTENTIALLY_INCREMENTAL descriptive context;
  published participation remains unavailable and no threshold is supplied.
- SMA200/strict stack and absent structural/CPR context: INSUFFICIENT_EVIDENCE.
- Agreement/confluence counts: INSUFFICIENT_EVIDENCE for added predictive value;
  not a score and not classified as highly redundant through an arbitrary cutoff.

Predictive value for EACH of SMA, VWAP, structure, volume, participation and confluence:
NOT_ESTABLISHED. No governed outcome/entry/exit/cost evidence supports win rate,
profitability, missed-winner, missed-trade or lost-profit conclusions.

## Minimum prospective design — no operational activation

Reuse the WO-06D population denominator and WO-06C same-observation Assessment pair.
Every admitted opportunity stays eligible, including ignored/rejected/untraded ones.
Retain original phase, direction, subject, session, methodology and observation identity.
Proposed shadow capture occurs independently of admission/publication/current pointers;
missing feature data cannot alter admission or create any downstream authority.

| Field | Disposition | Need / evidence / new calculation / acquisition / compact record |
| --- | --- | --- |
| Phase + existing local structure + NIFTY relationship | RETAIN_PROSPECTIVELY | Context/stratification; already governed; no new calculation or Provider request; deterministic; compact existing states |
| Narrow CPR width state | RETAIN_PROSPECTIVELY | Preserve existing gate context; already governed; no new calculation/acquisition; deterministic compact state |
| 5M SMA20 side | RETAIN_PROSPECTIVELY | One bounded trend-context comparison; research calculation from exact closes; no new acquisition if 20 completed closes already retained; otherwise unavailable; deterministic compact state |
| 5M VWAP side | RETAIN_PROSPECTIVELY | One volume-weighted context comparison; new approved research calculation; no new request if full current 5M OHLCV already retained; otherwise unavailable; deterministic compact state |
| SMA50/SMA200 side, all SMA slopes and strict stack | RESEARCH_ONLY | Do not enlarge default capture; insufficient/full-lookback concerns; evaluate before requesting more history |
| VWAP slope/distance | RESEARCH_ONLY | Exact but avoid storing every correlated derivative by default |
| Raw volume change / normalized ratio | RESEARCH_ONLY | Available counts do not justify participation thresholds or mandatory capture |
| Repeated directional vote/indicator count | REDUNDANT | Do not duplicate the compact states as a fabricated score |
| Break/retest/return-through/explicit range | NOT_ESTABLISHED | Exact cohort-linked event/range authority absent |
| Historical directional/Virgin/multi-day CPR | NOT_ESTABLISHED | Required chronological CPR history absent |
| Index VWAP / index traded volume | NOT_AVAILABLE | No proxy substitution |

The RETAIN_PROSPECTIVELY entries are recommendations for later authorization, not
new operational persistence. Feature availability and calculation version belong
with each compact state. Do not request extra Provider history in this slice.

For separately approved SMA research: exact timeframe, subject/native contract,
ordered completed source candles and boundary; 20/50/200 values require 20/50/200
closes; five-bar slope requires 25/55/205. No excess history merely for possible
future utility. For VWAP: canonical native subject, exact session/open/windows,
observation boundary, complete same-session 5M H/L/C/V, completion/source/integrity,
formula/reset identity and last completed feature timestamp. Missing volume or
coverage remains unavailable. For structure: reuse exact source barriers/ranges,
completed crossing/retest chronology and confirmation boundaries; no guessed range.
For participation: preserve raw volume and existing prior20 policy; any qualitative
threshold needs its own authority. Same-time historical normalization needs governed
comparable prior sessions, not rows selected by price movement.

A later outcome study needs an independently governed outcome horizon/price, timestamps,
source identities, complete availability accounting and dependence-aware grouping.
Pre-register cohorts and metrics before observing outcomes; do not select winners.
Shadow capture does not create Review, Readiness, Promotion, Risk, PAPER/LIVE or broker authority.

## WO_06G_RESEARCH_INPUT_REGISTER

AVAILABLE as retained machine inputs: completed OHLC, raw volume where meaningful,
exact candle/session/timeframe/source identities, phase, direction, existing NIFTY
relationship, original CPR width and WO-06F SMA/VWAP context where established.
DERIVABLE for a later authorized slice: total range H-L, body abs(C-O), body sign,
upper/lower wick from max/min(O,C), open/close location and body/wick ratios with
zero-range handling; exact adjacent-candle geometry. No pattern classifications or
pattern-effectiveness study is implemented here. Exact barrier/range events and
complete missing CPR/long-SMA history require their own evidence, not approximation.
Hero/Bahubali, rejection, engulfing, indecision/compression, impulse, reversal,
breakout failure and break-retest-hold/fail are handover topics ONLY for WO-06G.

## WO_07_VISUAL_RESEARCH_HANDOVER

After WO-06H, preserve machine ownership of exact OHLC, CPR/SMA/VWAP arithmetic,
volume and deterministic geometry. Potential visual questions concern clean/messy
structure, meaningful location, break/retest quality, acceptance/return-through,
orderly pullback, follow-through and explicit ambiguity/unobservability. Bind those
observations to the exact chart revision and time. Do not ask an Analyst to invent
missing machine values. No Question Pack, chart transport or Analyst contract changes
occur in WO-06F. WO-08 remains reserved for TradingView/Astra and is no dependency.

## Retention and monthly compatibility

Raw source evidence, row matrices and intermediate results are TEMPORARY: current
month plus five calendar days. September evidence is eligible from 6 October only
AFTER prior monthly Excel finalization, reconciliation and integrity verification.
No purge is performed. Permanent source/tests/governance retain compact conclusions,
not a duplicate raw candle archive. Source digests are reproduction references,
not a claim that deleted source bytes can later be recovered.

Future Sponsor Excel keeps Date, Security Name, Direction, Assessment Time,
Assessment Price, EOD Price, Move %, Outcome. Outcome fields remain unavailable
until authoritative evidence exists. Optional compact Phase/CPR/SMA/VWAP/Structure
context must not turn it into an internal identity dump. No workbook, ledger
persistence, download route or purge engine is implemented in this slice.

## Candidate and qualification

Four new Intraday-owned paths: pure research measurements, read-only application
adapter, isolated tests and this document. Existing source bytes are unchanged.
No shared/Swing behavior or chart/runtime composition is changed.

Focused qualification covers exact lookbacks, five-bar slopes, strict ordering,
VWAP arithmetic/reset/zero volume, source/boundary integrity, contract mismatch and
ambiguity, immutable CPR input, deterministic bytes, missing denominators and
agreement/conflict semantics. Existing structural/retest and production suites are
run unchanged for regression. Full results and candidate hashes accompany the
85-item engineering evidence pack; publication remains separately gated.

Recommended WO-06H disposition: SMA20/50 and research VWAP side are
PROSPECTIVE_SHADOW_CANDIDATE; slopes/distance/volume and descriptive confluences
RESEARCH_ONLY; SMA200/stack and missing structural/CPR context NOT_ESTABLISHED.
No feature is promoted to production by this document. WO-06G requires its next
Sponsor authorization; WO-06H/07/08/09, Statistics, purge, WO-10 and WO-18 remain held.
