# WO-06C — Assessment Price and Assessment Time provenance

**Status:** Implementation candidate under explicit Sponsor/EA WO-06C engineering authorization; publication review pending.

## Frozen meaning and forensic finding

Assessment Price is the authoritative market-price observation available to KRONOS at admission into Probables. Assessment Time belongs to that same observation. An analysis boundary, candle-completion time, operation time or publication time cannot replace it.

The accepted read-only forensic inspected 33 retained admissions: 15 LONG and 18 SHORT; 29 under methodology 2.1.0 and four under 2.0.0. All 33 are `PRICE_NOT_RETAINED`: no explicit pair and no nondiscretionary governed same-observation recovery rule were proven. The eight current candidates are included. The absence of a named field alone was not the conclusion: exact admission mappings, selected OHLCV evidence, phase rules, integrity and chronology were inspected. Opening had two admissions, Structure one, established phases 30. Native CRUDE and COPPER were included; no admitted NIFTY/BANKNIFTY production sample was present.

Opening comparisons use completed 15M evidence, 5M evidence and prior completed 1H context; the rules do not designate a single comparison price as the measurement anchor. Structure and later hourly/established evidence likewise do not designate such an anchor. Neither 15M close nor 5M close can be selected after the fact.

## Prospective contract and versioning

New `ProbablesV2Store.retain_complete` persistence retains an immutable `ProbablesAssessmentObservations` companion under `probables-v2/assessment-observations-v1/<run identity>.json`. Its schema is `KRONOS-INTRADAY-ASSESSMENT-OBSERVATIONS`, version **1.0.0**. Each admitted observation binds exact run/result identity, canonical subject, direction, phase, session, analysis boundary, source mapping and methodology version. Run identity/integrity and ordered exact admission membership are checked. Duplicate admission identities fail closed; repeated subjects in distinct runs remain distinct.

The contract contains Assessment Price, matching time, source identity, classification and proof. `PRICE_NOT_RETAINED` requires all price/time/proof/derivation values to be null with an explicit reason. Zero is never used for missing data. Measurement availability is not an admission filter.

A complete positive proof retains its own integrity, exact source identity/digest, authority-publication identity, canonical subject, run/admission/mapping/session, exact Decimal price, observation time and availability time. Both times must be available by the existing analysis boundary. Persisted classification requires that exact pair. Derivable classification permits only identity extraction of the **already designated observation's** price/time (`EXACT_DESIGNATED_OBSERVATION_PRICE_AND_TIME`); it grants no arithmetic, candle choice or reconstruction rule. Wrong-subject numerically equal prices, foreign run/mapping/session, future observations, missing pair halves and ungoverned source types fail closed.

**No positive production adapter is commissioned.** The current producer has no established designated admission-price source, so its sole wired constructor creates `PRICE_NOT_RETAINED` with reason `ADMISSION_PRICE_OBSERVATION_NOT_DESIGNATED`. Positive contract tests use explicit isolated source/authority fixtures, not real authority. A hash proves integrity, not market-source authority. A future positive adapter must be separately governed and resolve genuine source authority; a UI string or a constructed test object cannot commission it. This candidate does not make current OHLCV, current LTP or any downstream price authoritative.

New current pointers use the separately typed `AssessmentBoundProbablesV2Pointer`, schema version **2.1.0**, binding the manifest identity. Legacy pointer class/version **2.0.0** remains supported byte-for-byte. Missing/tampered manifest evidence behind a bound pointer fails restoration; persistence failure leaves the previous current pointer unchanged. The existing Probables run/result/mapping schemas and hashes remain unchanged. Methodology remains **2.2.0**; no analytical version change.

## Historical and replay rules

A run already present on disk is never backfilled by `retain_complete`, even if its companion is absent. Restoration only reads; absent historical companion means no retained assessment provenance. No price/time is derived from missing historical fields. Existing run/result hashes and original methodology versions are preserved. An identical new-run replay retains identical companion bytes and pointer identity. Existing protected historical replay fixtures continue to apply; the pre-existing 2.0 MCX commissioning replay caveat is not repaired here.

## Boundaries and qualification

The producer does not accept a Browser price, external resolver, Review/chart/Answer/WO-10/broker/entry/EOD value or later quote. LONG/SHORT use identical provenance rules. Exact NIFTY/BANKNIFTY subjects do not accept derivatives or proxies; MCX native and reference subjects remain separate. Source binding from WO-06B and Opening 09:30 behavior from WO-05A/WO-06A are unchanged: first 15M and three 5M candles complete; forming current-day 1H excluded; prior completed 1H allowed.

Deterministic tests cover positive proof serialization, exact matching time distinct from analysis boundary, missing values, wrong sources, future data, immutable persistence, restore, replay, duplicate/foreign binding, pointer tamper/loss, write failure, legacy absence, phases, directional/index symmetry, native MCX separation and 09:30 pipeline persistence. Positive tests establish contract validation only, not production price availability.

Statistics, EOD measurement, outcomes, WO-06D/E/F/G, CPR effectiveness research, VWAP, WO-10 and WO-18 remain held. No source acquisition, Provider/OpenAI/broker operational calls or runtime restart is required to qualify this candidate.
