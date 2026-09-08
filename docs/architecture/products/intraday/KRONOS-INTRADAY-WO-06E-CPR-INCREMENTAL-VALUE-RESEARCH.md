# WO-06E — Narrow CPR incremental-value research

Status: research/engineering candidate; publication review pending. 2026-09-08.

## Authority and scope

Sponsor's direct WO-06E implementation authorization supersedes the earlier
WO-06D “do not start WO-06E” boundary. This research does not change production
methodology 2.2.0 or the mandatory Narrow CPR gate. WO-06A Opening combined
support, WO-06B source binding, WO-06C admission-only Assessment capture and
WO-06D full-population authority remain unchanged. No runtime wiring is added.

Authority was reconciled against the current source, WO-06A/B/C/D documents,
Current Authority Manifest, historical phase-aware/research contracts and the
Living Master. Older WO-06E phase-aware production documents remain historical
authority; this separately named research document does not replace them.
The direct current Sponsor decisions and published successors resolve stale
programme-status text. Source baseline: `979c9661926fad8eec96f9e71906713e835c0c21`.

## Method and source proof

Two research arms consume the same immutable mapping. A reviewed transcription
of the historical evaluator changes only the two Narrow CPR gate conditions.
An AST comparison test proves that statement. An evaluator-source hash requires
new review if production rules change. Every eligible retained baseline must
match both the research transcription and the governed evaluator exactly:
state, direction and ordered reasons. Original 2.0.0/2.1.0 Opening behavior is
preserved; no 2.2.0 historical observation exists in this cohort. Tests cover
2.2.0 separately without upgrading historical evidence.

Exact CPR identity, integrity, selected previous Daily, canonical subject,
previous/current session, source integrity, H/L/C and temporal availability are
checked. The formula is reproduced exactly; missing facts, ambiguous envelopes,
source mismatch or unreproduced baselines remain explicitly ineligible. No
latest-file fallback, synthetic producer artifact or current-pointer write exists.
Other retained semantic evidence, including historical NIFTY relationships, is
held fixed under its original publication; this research neither repairs nor
upgrades legacy factual authority. Baseline source limitations remain limitations.

Unavailable rows retain their original state/reasons. Old held MCX observations
are not reinterpreted through subsequent commissioning. Evaluable MCX rows must
retain the matching commissioning publication/provenance and effective boundary.
MCX is reported separately and remains deferred for an NSE-first research policy
conclusion. It is not pooled with NSE to claim a larger predictive sample.

## Exact governed CPR definition

For the exact selected previous completed Daily H, L and C:

- P = (H + L + C) / 3.
- BC_raw = (H + L) / 2; TC_raw = 2 × P − BC_raw.
- Lower = min(BC_raw, TC_raw); Upper = max(BC_raw, TC_raw).
- Half width = abs(P − BC_raw); total width = Upper − Lower.
- Normalized half width = half width / C × 100; likewise total width / C × 100.
- **Narrow iff half width < 0.001 × C**, strictly; normalized half width < 0.1%.

Production uses Decimal arithmetic without quantization or an explicit local
precision override. Research fixes precision 28 / ROUND_HALF_EVEN, reproducing
all 572 retained facts exactly. No tolerance or alternative formula is introduced.
The selected previous session follows governed session evidence, not date-minus-one.
The same exact Daily fact may lawfully support multiple phases/refreshes.

In exact algebra, half width = abs(2C−H−L)/6 = abs(C−(H+L)/2)/3.
It measures the close's displacement from the previous range midpoint. A wide
range can have zero CPR width when C is at that midpoint. CPR width is not ATR,
volatility, liquidity or a synonym for range compression. Finite-precision results
remain those of the governed implementation, not a substituted algebraic evaluator.

## Complete denominator and matched counts

9 runs × 98 members = 882 raw subject/run observations. Discovery factually
evaluable: 670; source unavailable/failed: 212. Retained mapped admission
assessments: 666; unmapped: 216. Probables evaluable and counterfactual eligible:
572; unavailable: 310. All 572 baselines and CPR source bindings reproduce.
Unavailable: 212 source Discovery, 4 mandatory evidence, 83 NIFTY context,
11 MCX commissioning. No evaluable row is silently dropped.

| Comparison | Count |
|---|---:|
| Baseline admitted | 33 |
| No-CPR admitted | 107 |
| Additional / CPR sole blocker | 74 |
| Removed | 0 |
| Unchanged admitted | 33 |
| Unchanged rejected | 465 |
| Narrow | 169 |
| Non-Narrow | 403 |
| CPR plus another blocker | 329 |

Baseline admission is 5.77% of eligible observations, versus 18.71% without CPR.
CPR alone changes admission for 12.94% of the eligible denominator and excludes
69.16% of the 107 otherwise-qualified observations. Of 403 non-Narrow rows,
329 still fail another requirement. Feature prevalence does not prove benefit.

| Phase | Evaluable | Baseline | No CPR | CPR-only additions |
|---|---:|---:|---:|---:|
| OPENING | 87 | 2 | 11 | 9 |
| STRUCTURE | 7 | 1 | 1 | 0 |
| CURRENT_SESSION_ESTABLISHED | 478 | 30 | 95 | 65 |

FIRST_CURRENT_SESSION_1H has no eligible historical row; it is tested, not imputed.
The complete denominator also retains 83 unavailable Opening rows, 2 Structure,
9 Established, and 216 with no governed phase retained.
CPR-only exclusion rates are 10.34% Opening, 0/7 Structure and 13.60% Established.
65/74 additions occur in Established, where most observations also occur.
This is descriptive concentration, not proof of a phase interaction.

| Fixed baseline direction | Evaluable | Baseline | No CPR | Additions |
|---|---:|---:|---:|---:|
| LONG | 79 | 15 | 51 | 36 |
| SHORT | 104 | 18 | 56 | 38 |
| NON_DIRECTIONAL | 355 | 0 | 0 | 0 |
| CONFLICTING | 34 | 0 | 0 | 0 |

No historical row changes direction between arms. LONG/SHORT rules are symmetric;
observed exclusion rates are 45.57% and 36.54% of their directional denominators,
or 70.59% and 67.86% of otherwise-qualified observations. No cause is inferred.
The 310 unavailable rows retain absent direction rather than neutral substitution.

| Subject type | Raw | Evaluable | Baseline | No CPR | Additions |
|---|---:|---:|---:|---:|---:|
| NSE equities | 819 | 540 | 31 | 100 | 69 |
| NIFTY | 9 | 6 | 0 | 2 | 2 |
| BANKNIFTY | 9 | 6 | 0 | 2 | 2 |
| MCX, separate/deferred | 45 | 20 | 2 | 3 | 1 |

NSE-only: 552 eligible, 31 baseline, 104 no-CPR, 73 additions, 318 CPR-plus-other.
MCX: COPPER 5 eligible / 1→1; CRUDE 6 / 1→1; GOLDM 4 / 0→0;
SILVERM 5 / 0→1; NATGAS 0 eligible. All 25 MCX unavailable observations stay unavailable.
The single MCX addition provides no basis for a cross-market effectiveness claim.

The 74 CPR-only additions cover 46 distinct subjects. Largest raw counts:
HCLTECH 4/6 evaluated; MAZDOCK, MUTHOOTFIN, PERSISTENT and UPL each 3/6;
POWERINDIA 3/5. Fifty-two governed subjects have no additions in the retained
cohort, which does not prove zero future effect or adequate sampling.

## Dependence, dates and feature distribution

WO-06D proposed contiguous subject/session/direction grouping is reused only as
research projection. Baseline: 33 raw admissions / 33 episodes. No CPR: 107 raw /
105 episodes, including two persisted observations and one direction-change event.
Subject/session/direction groups also number 33 and 105. Neither episodes nor
these groups are asserted statistically independent. Phase changes within an
episode, disappearance, re-entry, unavailable gaps and coverage safeguards retain
WO-06D semantics. No authoritative admission denominator changes.

Five trading dates: Aug 28, Aug 31, Sep 1, Sep 4 and Sep 7, 2026. Descriptive
chronological partition: first three dates 279 eligible / 15→50 admissions (+35);
last two dates 293 / 18→57 (+39). Complete subject/session groups stay together.
No random split, tuned threshold, meaningful predictive holdout or generalization
claim is possible from five dates and absent outcomes. The 310 unavailable rows
remain in the full denominator. The convenience trading_date field is populated
only for eligible rows; its null value on unavailable rows is not a claim that
their source date is absent. Their exact governed session identity is retained.

Normalized governed half-width percentages (display rounded only):

| Population | n | min | Q1 | median | Q3 | max |
|---|---:|---:|---:|---:|---:|---:|
| All eligible, audit total | 572 | 0 | 0.082919 | 0.179157 | 0.308073 | 1.783195 |
| NSE only | 552 | 0 | 0.085523 | 0.182159 | 0.309180 | 1.783195 |
| MCX, separate | 20 | 0.008463 | 0.082810 | 0.133835 | 0.204735 | 0.346808 |
| Distinct subject/previous-session contexts, audit total | 473 | 0 | 0.078287 | 0.179124 | 0.317291 | 1.783195 |

Quantiles use linear interpolation at q×(n−1), without a normality assumption.
169/572 are Narrow; after collapsing identical subject/previous-session context,
142/473 are Narrow. Different refresh candle identities are preserved in temporary
row references; agreeing Daily contexts are counted once for the sensitivity view.
No conflicting context values were found. Raw half-width points range 0–787.666667
(median 1.975); unlike normalized percentages, mixed instrument price units are
not interpreted as comparable feature magnitudes.

Prior range comparison is (H−L)/C×100, descriptive only. NSE equities have median
prior ranges 1.490385% for Narrow and 2.035149% for non-Narrow, with overlapping
ranges 0.646802–4.284423% and 0.655807–10.699171%. MCX medians separately are
2.096177% and 2.217515%, also overlapping. Across the 473 distinct Daily contexts,
medians are 1.470650% and 2.053712%. This cohort shows different centers and
substantial range overlap, not equivalence or a commissioned compression filter.
There is no approved compression threshold, inferential test or causal claim.

## Outcome conclusion and prospective requirement

**Retained evidence establishes decision impact, not predictive value.** All 33
baseline admissions remain PRICE_NOT_RETAINED. PRICE_OUTCOME_RESEARCH and
predictive effectiveness are NOT_ESTABLISHED. No historical price/time is
backfilled. CPR-only exclusions are not labelled missed winners, trades or profits.
No recommendation to remove or retain CPR on profitability grounds is supported.
Production Narrow CPR therefore remains unchanged under existing authority.

A future separately authorized study should use the complete governed NSE
population at predeclared observation times, retaining baseline admissions and
CPR-only shadow decisions with identical other evidence. Start with at least one
complete prospective calendar month covering all governed phases and both
directions; this is an operational collection horizon, not statistical sufficiency.
Review coverage, missingness, dependence and precision before choosing any larger
sample requirement or untouched later chronological evaluation period. Do not
select only reviewed, traded, available-outcome or winning observations.

WO-06C captures genuine price/time only after production admission. It does not
capture the 74 historical shadow observations and does not authorize future shadow
quote acquisition. A separate research-only authority would be required for exact
subject/source-bound contemporaneous price and timestamp from the same observation,
with server receipt/availability, run/mapping/decision identities, method version,
CPR classification, provenance, integrity and request-accounting evidence.
Any paired capture timing/latency difference must be retained, not backdated away.
Failure remains PRICE_NOT_RETAINED, never a production admission or sample filter.
No production Probables, pointers, Review or trading authority may be created by
shadow capture. The mechanism is proposed only and is not implemented here.

EOD price/time/source/session/endpoint and coverage authority must be commissioned
separately, along with any direction-aware move/outcome definitions. MFE, MAE,
time-to-move and path outcomes are not implemented. Preserve all missing rows;
report evaluable outcome coverage without equating missing with zero return.
Use subject/session or justified episodes, date clusters, chronological evaluation
and phase/direction stratification; do not randomly divide repeated observations.
Statistics/Excel, WO-10 and WO-18 remain held; WO-06F is not started.

## Reproduction, retention and qualification

The read-only entry point is
`kronos.application.intraday_cpr_research.analyze_retained(evidence_root)`.
It returns compact research data in memory; no runtime route, Provider operation,
producer persistence or currentization is wired. During the approved retention
window, run it against the same immutable source population and exact replay
envelopes. Full source rows are not duplicated into GitHub. Temporary projections,
logs, candidate hashes and this qualification's detailed report are working
research outputs, not a new permanent raw archive.

Retention: current month + five calendar days; purge only after the previous
monthly Excel is finalized, reconciled and integrity verified. No purge engine is
implemented. Permanent categories remain source/tests/governance, Living Master/
programme governance and final monthly Sponsor Excel. If retained source evidence
is lawfully purged later, do not claim that compact aggregates alone reconstruct it.

Focused tests cover exact two-gate isolation, historical/current Opening truth
 tables, later-phase direction/coherence, sole/multiple blockers, subject/index
identity, source/formula integrity, absent evidence, MCX hold, baseline drift,
raw/dependence projection, read-only adapter and deterministic quantiles.
Production source files and historical evidence are unchanged; qualification
results and exact candidate hashes accompany the Sponsor/EA evidence pack.

## Exact historical run references

All identifiers below have prefix `INTRADAY-PROBABLES-V2-RUN-`.

| Suffix | Version | Evaluable | Baseline | No CPR |
|---|---|---:|---:|---:|
| `63B5EBEA43E31839BAAD3C112DFEC1D012A88D47408297248B3B1C2FD495D4EB` | 2.0.0 | 93 | 4 | 17 |
| `8323DEA36A1138EDA2325F7BC37EAD6CE1405FD3934EA2DDADD5B35227F4A7EF` | 2.1.0 | 95 | 8 | 21 |
| `EDA42040367A41391198F622AA762024B5D97E842C84E83485F5B33094FB2FB2` | 2.1.0 | 91 | 3 | 12 |
| `09216E64574759448A9755B421325DA999FC62944496EBDD467A725DF3EFF926` | 2.1.0 | 0 | 0 | 0 |
| `B8050AD9301859BC0FB4C5B7ABDEC0CC40CC09F3801EC53C148918EA44EEE302` | 2.1.0 | 0 | 0 | 0 |
| `4F165A8CCBC9C0549F72BEE32785BEC9271AECB46ED4E284E181F32ECB14B412` | 2.1.0 | 3 | 0 | 0 |
| `8851D8123866C06C3D54B0268FF7826DE34171BF6FC5EC26D241F5831488BF03` | 2.1.0 | 96 | 1 | 8 |
| `8DC2835D0D7A53490F8ABA536B74706858E47F49FDCFB51156DD08D17CF6D372` | 2.1.0 | 97 | 9 | 28 |
| `35EA4FEE81D7368AE2441A794479F294A0C02B8239DAED71525420EAFA151F85` | 2.1.0 | 97 | 8 | 21 |

Research result identity: `WO06E-RESEARCH-1d118f57ed95cc58a4d304e97a635ed1dc72cad5f6262a90d6bd7eddb314b015`.

Final qualification: 502 focused, 1,052 affected and 6,245 active-suite tests PASS.
All 75,011 baseline production files remain byte-identical, including 72,054
Intraday files; no Intraday additions. Nine concurrent/unattributed Swing additions
(six monitoring, three notification records) are preserved. Initiating actor is
NOT_ESTABLISHED; carry forward to deferred Swing/shared hardening, not attributed
to WO-06E. No operational calls, production restart, staging, commit or push.

## Sponsor full-context amendment — 2026-09-08

Status: Sponsor definitions approved; bounded research implementation candidate.
The masterclass Google Drive document is research input only. The Sponsor's
explicit CPR definition decision controls these research definitions, without
changing any existing KRONOS production vocabulary or admission authority.

### Approved deterministic definitions

Direction uses both bounds: ASCENDING iff current lower > previous lower AND
current upper > previous upper; DESCENDING iff both are strictly lower. All
other proved cases are MIXED_OR_NOT_DIRECTIONAL. Pivot movement alone and full
band separation are not direction definitions. No tolerance is introduced.

Geometry retains independent containment predicates: CURRENT_INSIDE_PREVIOUS
uses >= lower and <= upper; CURRENT_CONTAINS_PREVIOUS uses <= lower and >= upper.
Exact equal bands therefore truthfully satisfy BOTH predicates. This is not an
exclusive histogram; no arbitrary precedence discards either Sponsor rule.
OVERLAPPING means intersection without either containment. Disjoint bands are
NON_OVERLAPPING_ABOVE when current lower > previous upper, or
NON_OVERLAPPING_BELOW when current upper < previous lower. Edge equality is a
touch, hence overlap unless a containment predicate also applies. No existing
OUTSIDE label is overwritten. The masterclass's separated-band meaning maps
only to the two explicit NON_OVERLAPPING states in this research.

Virgin CPR requires exact governed active-to-observation trading windows and
complete interval coverage. For any price interval, high >= band lower AND
low <= band upper establishes touch, including exact equality. Complete history
with touch yields NO; complete history without touch yields YES. Missing windows,
missing active time or incomplete coverage yields NOT_ESTABLISHED, even if an
available fragment touches. Future intervals reject before their OHLC is used.
No clock, market acquisition, chart interpretation or guessed calendar is used.
The pure research classifier consumes explicitly resolved governed windows;
it does not itself confer authority on caller-supplied windows or source labels.
The historical adapter supplies no invented windows.

Two-/three-day Narrow require all respective CPR facts and exact consecutive
DOMAIN-008 trading-session identities, newest first. Exact predecessor linkage
is required; no date-minus-one, calendar-day adjacency or weekend/holiday reset.
Any absent required member yields NOT_ESTABLISHED, never NO. When all source,
subject, sequence and boundary checks pass, all Narrow yields YES, otherwise NO.

Price location consumes already-retained exact relationships to lower and upper
bands only: above both = ABOVE; below both = BELOW; between/on band = INSIDE.
Missing comparisons yield NOT_ESTABLISHED and inconsistent comparisons reject.
No price is reconstructed or substituted. Research inputs and synthetic tests
are not historical facts or new governed producer artifacts.

### Historical availability and original result preservation

The separate Intraday-owned context adapter invokes the unchanged original
counterfactual and retains its research identity. It validates the exact
run/methodology replay envelope, subject, mapping/boundary and CPR identity.
It inventories the existing one-Daily V2 source contract. Expanded source or
unexpected semantic families fail closed for explicit adapter review instead
of being silently ignored. No legacy latest-file/subject-only join is used.

All 572 eligible observations retain one previous-session Daily candle.
The 465 legacy semantic artifacts checked during reconciliation have zero exact
source-bundle/subject/boundary matches to these observations. The accepted V2
semantic families have no authoritative CPR price-location relationship.
No unrelated artifacts, later observations or external data fill those gaps.

Across all 572: width/Narrow EXACTLY_RETAINED; price-normalized width and
previous-range-normalized width DETERMINISTICALLY_DERIVABLE_FROM_SAME_GOVERNED_EVIDENCE.
Direction, geometry, price location, two-day/three-day Narrow and exact ATR
inputs are NOT_RETAINED in the selected contracts, so their research results
are NOT_ESTABLISHED. Virgin complete-history proof is NOT_ESTABLISHED.
Unknown does not become mixed, overlapping, non-virgin, false or zero.

The original 572 / 33 / 107 / 74 / 329 / 0 counts and research identity are
unchanged. All 33 historical Assessment Prices remain PRICE_NOT_RETAINED.
The 74 sole blockers are 36 LONG and 38 SHORT; phase distribution is Opening 9,
Structure 0, Established 65. Baseline is 15 LONG / 18 SHORT, and phase 2/1/30.
Width medians (governed half-width percent) are 0.055031446541 for baseline and
0.217632080316 for sole blockers. Prior-range percentage medians are respectively
1.529224129843 and 1.978134784089. This separation partly follows the gate used to
select the groups; it is not an independent predictive result.

All broader-context fields are NOT_ESTABLISHED for both populations; no inferred
context subgroup, directional coherence signal or admission replacement is
claimed. Phase comparison remains Opening 2→11, Structure 1→1, Established 30→95.
NIFTY and BANKNIFTY each have six eligible observations and 0→2 admissions, with
broader context unknown. MCX remains separate: 20 eligible, 2→3, one sole blocker.
NSE equities have 540 eligible and 31→100; index facts are not derivatives facts.
Exact 74-row and 33-row deep dives, per-subject, phase/direction breakdowns and
all source identities are in the temporary revised evidence pack/projection.

### Width normalization and mathematical relationship

Percent normalization uses the same retained previous-session close, never an
Assessment Price. Range-normalized full width uses full width / (H−L), excluding
zero ranges only from that ratio (zero observed in this cohort). No ATR is
invented. Finite-precision retained decimal values are preserved, including
negligible rounding near the theoretical one-third full-width/range maximum.

Pearson and average-tie-rank Spearman compare full-width percentage with
previous-range percentage. NSE raw n=552: Pearson 0.829216, Spearman 0.640340;
deduplicated subject/previous-session n=459: 0.841383 / 0.664324. MCX raw n=20:
0.131602 / 0.212443; distinct n=14: 0.322808 / 0.424176. Full-width/range medians
are NSE raw 0.217328, distinct 0.213752; MCX raw 0.112584, distinct 0.098002.

These percentages share a denominator; repeated subjects/sessions and unequal
market samples limit interpretation. Correlation is descriptive, not causal,
independent-sample significance or predictive value. A close at the prior range
midpoint gives zero CPR width even for a wide range. Narrow is not synonymous
with low prior volatility. No threshold tuning or production score is added.
Raw no-CPR 107 admissions still represent 105 proposed episodes; the 74 sole
blockers represent 72 subject/session/direction groups, not 74 independent tests.

### Prospective recommendation and boundaries

Reuse compact exact CPR source/policy identity, target/previous-session identity,
lower/upper bounds, governed width and Narrow classification. Broader research
requires explicit predecessor CPR identities, separately governed analysis-time
price-context source/timestamp, and for Virgin an active time plus complete
coverage proof. Capture derived context and availability only when those inputs
actually exist; a stored assertion alone is not proof. ATR requires exact
period/method/source authority before inclusion. No automatic permanent field
expansion or production capture change is made by this research amendment.

Temporary research projections follow current-month + five-days retention and
conditional finalized/reconciled/integrity-verified monthly Excel purge gating.
No permanent raw archive, purge engine, monthly Excel, SMA, VWAP or WO-06F is
implemented. Predictive value remains NOT_ESTABLISHED. Production Narrow CPR,
2.2.0, source binding, Assessment authority, 09:30 Opening and all runtime wiring
remain unchanged. Publication is not authorized.

### Full-context qualification result

New deterministic cases: 57/57 PASS. CPR/context/population focused: 591/591 PASS.
Affected Intraday/Browser: 530/530 PASS. Complete active suite: 6,302/6,302 PASS
in 1,089.30 seconds. Source/test hashes unchanged through full qualification.
Exact retained-context reproduction PASS. Syntax/compile, diff/whitespace and
changed-scope secret-pattern scan PASS (zero findings; not exhaustive assurance).
