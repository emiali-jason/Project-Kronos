# WO-06D — Candidate population and measurement foundation

**Status:** Sponsor-authorized engineering candidate; publication review pending. Research episode rule below is a proposed deterministic grouping, not commissioned analytical methodology.

## Accepted activation and boundaries

Sponsor disposition: WO_06D_RUNTIME_ACTIVATION = ACCEPTED_WITH_RECONCILED_SIDE_EFFECTS; WO_06D_CAN_CONTINUE = YES. PID 21692 loaded revision 2b7bf26beb83ac5a1a0dc9f0a420b0bf6950ac25 as CLEAN_COMMIT. WO-06C remains complete/published/loaded. Seven Swing files remain genuine activation evidence; historical initiating actor is unknown and the attribution gap is closed. Prospective connection audit and maintenance notification policy are recorded in the Shared Platform Hardening Register and Swing Post-Intraday Improvement Register, deferred outside WO-06D.

No new runtime restart, Provider connection/acquisition, Refresh, live Probables, Review, Answer import or broker action is part of this candidate. No WO-06E/F/G, CPR comparison, VWAP computation or Statistics UI/Excel is implemented.

## Immutable raw population and capture

One admission observation is the exact Probables run plus admitted result identity, exposed as an integrity-derived INTRADAY-ADMISSION-OBSERVATION identity. The producer remains authoritative; source documents are retained unchanged. WO-06C already persists one AdmissionAssessment per EVERY newly admitted result before currentization, including failed quotes as PRICE_NOT_RETAINED. WO-06D reuses this existing immutable persistence equivalent instead of adding another quote engine or changing admission/publication policy.

The read-only IntradayPopulationMeasurement adapter validates original run/result/mapping/selected evidence lineage and the exact WO-06C companion. It preserves all evaluated results, including non-admission and unavailable reasons, and all original mappings with completed OHLCV/semantic/Opening/NIFTY/source-binding evidence. There is no dependence on Review or trading selection. No future policy re-evaluation is used to explain old reasons.

Assessment Price and Time come from the same WO-06C governed observation. Quote failure leaves the admission in the denominator. Historical companion absence yields a missing projection and never a source write/backfill. Publication/run identity is exact; a standalone publication/admission timestamp not retained by the original producer is NOT_RETAINED. Analysis boundary is not relabelled as Assessment Time. Trading date is taken from current-session selected candle dates only if unambiguous; governed session identity is retained independently.

## Derived persistence and restoration

MeasurementPopulation is an immutable, validated snapshot containing the original run, exact mapping population, optional exact assessment companion and optional exact source Discovery run. It has a versioned identity and deterministic encoding. Original contract parsing validates recursive integrity; foreign/missing/duplicate mappings, conflicting subject bindings and inconsistent counts fail closed.

PopulationMeasurementStore optionally retains these self-contained DERIVED_POPULATION_NO_TRADING_AUTHORITY snapshots under population-measurement-v1/<exact run>.json. Same bytes replay; different bytes at the same run fail closed. Atomic create-once publication follows the established WO-05B/WO-B hard-link pattern, including competing first writers; a failed write leaves no partially published snapshot. Restoration validates envelope, exact identity and original source contracts. No producer CURRENT pointer is written. There is no automatic historical materialization or Browser GET/export route; no production snapshot is generated in engineering. All prospective raw measurement rows already exist in the WO-06C producer companion, including missing-price rows, so optional downstream materialization cannot lose their denominator.

## Funnel and missing downstream facts

Keep original Discovery factually-evaluable/failure accounting separate from Probables evaluable/unavailable diagnostics. Admission-evaluated means a retained mapped member reached the Probables evaluator, including members later marked unavailable. Preserve governed population, admitted, not-admitted, unavailable and missing measurement independently. Missing source Discovery evidence is NOT_RETAINED, not zero.

Reviewed/rejected/promoted/traded evidence is not joined in WO-06D; it cannot change the admission denominator. Missing joins are explicitly DOWNSTREAM_EVIDENCE_NOT_JOINED or NOT_ESTABLISHED, never an asserted not-reviewed/not-traded outcome. Future joins require exact run/result identities and their own domain authority. The historical Review bound to 4 September remains non-current after the 7 September Probables advance. No new Review is generated.

## Proposed dependence-aware episodes

Policy label: WO06D-PROPOSED-CONTIGUOUS-SESSION-DIRECTION-V1. Input consists of complete retained run populations, ordered by analysis boundary; identical run replay is deduplicated, conflicting same-identity runs or distinct equal-time runs fail closed. Changed subject coverage fails closed instead of fabricating disappearance. Sparse retained history does not prove no omitted runs; population findings are conditional on the supplied retained cohort.

Within the same exact subject/session/direction, continuous admissions form one proposed research episode rooted in the first raw observation. Each raw observation remains separately addressable. Phase changes are retained alongside PERSISTED and do not by themselves start another episode. Direction changes create an explicit new episode. New session creates a new episode. Disappearance means only absence from the next admitted population (including unavailable); re-entry begins a new episode. No win/loss, setup invalidation or execution consequence follows. Same-subject/session episodes remain statistically dependent; grouping does not establish statistical independence.

Do not invent episodes inside historical producer artifacts. Proposed episode identities are downstream projection identities only. No automatic expiry, automatic carry-over, hindsight-dependent merge, sample-size target or trading rule is introduced.

## Feature and research boundaries

EXACTLY_RETAINED where mappings exist: phase, result direction/reasons, narrow CPR qualification and source identity, semantic 1H/15M/5M facts/roles/attributes, Opening combined/prior/5M relationships, NIFTY relationship/applicability, original selected candles, source/methodology/integrity identities. NOT_RETAINED applies where no mapping/feature exists; never fill it using a later methodology.

Deterministically derivable from the same run: current-session date when candle dates agree, raw population counts and longitudinal transitions within a complete ordered cohort. These are not new analytical admissions. CPR counterfactual readiness must be reported for the actual retained corpus; unavailable/failed pre-mapping members do not acquire hypothetical inputs. A fully mapped member may retain the needed non-CPR inputs, but this work performs no gate-removal evaluation. Missing prerequisites and commissioning/governance context must remain explicit in later matched research.

VWAP_RESEARCH_READY = NO for an outcome-effectiveness study now. Future governed work needs exact full-session candle/volume coverage (not merely selected terminal bars), session/timezone/open-close boundaries, approved VWAP anchor/formula and phase rules, exact admission/assessment linkage, feature snapshot, missing-data policy, dependent-observation grouping and authoritative later outcome evidence. Do not calculate or persist VWAP now.

EOD price, Move %, CORRECT/WRONG/FLAT/PENDING outcome labels, MFE/MAE/time-to-move, monetary P&L and realised R are absent. No Readiness, Promotion, Risk, Entry, PAPER/LIVE or broker authority exists here. Final Sponsor Statistics/Excel remains held until its later programme gate.

## Personal retention architecture

Permanent: final monthly Excel; GitHub source/tests/governance; Living Master/programme governance. Temporary: operational/analytical generated evidence, including WO-06C companions and WO-06D derived snapshots. Current month plus five calendar days is the retention window; previous-month purge requires its final monthly Excel to be finalized, reconciled and integrity verified. If finalization is incomplete or retained source dependencies are unresolved, do not infer purge permission. Historical dependencies/current pointers must be reconciled before a later purge engine acts.

A derived measurement snapshot retains its exact original source bundle so a future monthly reconciliation can bind totals, omissions and integrity without silently substituting surviving CURRENT records. This is not authority to retain operational copies permanently. WO-06D implements no purge engine, timer, deletion, monthly finalizer or Excel generator. Source availability failures remain explicit after any separately governed retention operation.

## Retained-corpus qualification (read-only)

Nine runs retain 882 subject/run rows across 98 governed subjects. Discovery accounting reports 670 factually evaluable and 212 unavailable/failed. Probables reports 572 evaluable, 310 unavailable, 33 admitted and 539 not admitted. Mapped admission evaluation reached 666 rows; 216 have no mapping (212 source Discovery unavailable and four mandatory-evidence unavailable). Of the mapped rows, 94 are unavailable: 83 NIFTY-context unavailable and 11 MCX-commissioning unavailable. These distinct funnels must not be conflated.

There are 33 raw admissions, 33 exact subject/session/direction combinations, zero repeated combinations, zero persistence sequences, one disappearance, zero re-entries, zero same-session direction changes and zero phase changes in this retained cohort. There are 30 distinct admitted subjects; three occurrences repeat subjects across different sessions. Proposed episode count happens to equal 33 here; the isolated sequence test preserves six admissions in four episodes, proving equality is not assumed. All 33 historical Assessment Prices remain PRICE_NOT_RETAINED; no backfill or price-based outcome calculation is possible for them.

Current authoritative Probables remains INTRADAY-PROBABLES-V2-RUN-35EA4FEE81D7368AE2441A794479F294A0C02B8239DAED71525420EAFA151F85, analysis boundary 2026-09-07T10:53:59.014257+00:00. Its eight admissions are YESBANK LONG, HINDALCO LONG, ADANIPORTS SHORT, HEROMOTOCO SHORT, KOTAKBANK SHORT, VEDL SHORT, NTPC SHORT and CIPLA LONG. All are established-phase, PRICE_NOT_RETAINED. The retained run was produced under methodology 2.1.0; the accepted runtime now contains 2.2.0 but no new Refresh has been performed. Do not relabel the retained run's methodology.

CPR_COUNTERFACTUAL_READY = YES for a bounded historical decision comparison on the 572 retained evaluable rows (552 NSE, 20 MCX), using their original 2.0.0/2.1.0 methodology, frozen non-CPR features and original MCX commissioning provenance. The feature inventory found no missing required non-CPR semantic/Opening/NIFTY snapshots in that evaluable cohort. This is evidence readiness only; no CPR gate-removal evaluation has been run. Do not use today's commissioning publication or 2.2.0 correction to rewrite their original eligibility. The other 310 rows remain unavailable, with the original reasons and denominator retained; the 216 unmapped rows cannot receive invented feature snapshots. A current-methodology 2.2.0 empirical study needs prospective observations, and price-outcome effectiveness remains unavailable for all 33 historical admissions.

All 666 mapped rows retain 1D context, 1H regime, 5M progression and directional coherence facts. They retain 496 established/structure 15M facts and 170 Opening-15M, Opening semantic and NIFTY snapshots. The 33 admissions retain 31 established/structure 15M and two Opening/NIFTY snapshots. Absence of an inapplicable NIFTY/Opening snapshot is not a fabricated neutral feature. VWAP data/readiness remains as specified above; no VWAP or outcomes work begins here.
