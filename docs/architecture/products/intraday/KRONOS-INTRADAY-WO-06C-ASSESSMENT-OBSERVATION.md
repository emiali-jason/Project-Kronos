# WO-06C — Assessment Price and Assessment Time provenance

**Status:** Sponsor/EA approved Assessment observation policy; revised implementation candidate pending qualification and publication review.

## Authority and historical finding

The Sponsor decision `KRONOS-INTRADAY-SPONSOR-ADMISSION-MARKET-OBSERVATION-V1` designates the authoritative current market observation for the exact analytical subject, captured in the same admission operation after methodology determines admission and before Probables publication/currentization. Assessment Price and Assessment Time are the indivisible price and Provider/market timestamp from that observation. This supersedes this document's earlier candidate limitation that no positive source adapter was commissioned. It does not grant execution, fill, Risk, P&L, outcome or broker authority.

The accepted forensic inspected 33 retained admissions: 15 LONG and 18 SHORT; 29 under methodology 2.1.0 and four under 2.0.0. All 33, including the eight current candidates, remain `PRICE_NOT_RETAINED`. Opening had two admissions, Structure one, established phases 30. Native CRUDE and COPPER were included; no admitted NIFTY/BANKNIFTY production sample was present. Exact admission mappings, selected OHLCV evidence, chronology and integrity did not establish an authoritative assessment pair. No historical values are reconstructed or backfilled.

## Current Provider observation and capture order

The Intraday-owned `ProviderDiscoveryFactualSource` retains the exact native `InstrumentRecord` already resolved for each governed member during the current factual operation. After the existing pure V2 evaluator determines all admitted results, `IntradayProbablesV2Application` invokes the bounded assessment capture adapter for every newly admitted result before retaining the run and current pointer. The adapter requests **one** existing DOMAIN-006 `ReadOnlyProviderLease.quote(record)` observation per admitted member. No additional instrument catalogue acquisition, analytical evaluation, Review selection or admission filtering is introduced.

The existing normalized `QuoteSnapshot.last_price` and `QuoteSnapshot.timestamp` supply the pair. The existing Kite adapter derives both from the same quote response item; it has no local-clock fallback for the quote timestamp. Untimestamped `LtpSnapshot`, OHLCV closes, later LTP, Review/chart/Answer/WO-10/broker/entry/EOD values are not eligible. Provider timestamp may be later than the requested analysis boundary because capture occurs after admission evaluation. Request/receipt times are retained separately for chronology and never substituted for Assessment Time. No arbitrary freshness threshold or clock tolerance is introduced.

The same operation retains its Provider lease through capture. Intraday V2 requests the existing `QUOTE` permission in addition to its existing instrument/history permissions. If the Provider capability cannot grant QUOTE, local lease negotiation falls back to the existing Discovery permissions; missing optional measurement capability cannot prevent admission. Legacy Discovery and historical/monitoring leases are unchanged. No shared Provider source, authentication, contract or broker behavior changes.

Every admitted opportunity is covered, independently of later review, rejection, promotion or trading. LONG/SHORT and all phases use the same path. Exact NSE index instrument records are required for NIFTY/BANKNIFTY, with index segment and no derivative/ETF proxy. NSE derivative records are rejected. MCX uses only the already governed native binding; this does not activate MCX or permit NYMEX/COMEX reference substitution. The returned quote instrument must exactly equal the resolved native request record.

Each failed acquisition, missing/malformed timestamp, invalid pair, conflicting instrument or unavailable binding retains `PRICE_NOT_RETAINED` with bounded reason `ADMISSION_MARKET_OBSERVATION_UNAVAILABLE`. No partial pair, raw exception, retry, later lookup or candle fallback is retained. The admitted candidate remains admitted with unchanged direction. Capture continues for remaining admissions. Storage/integrity failure does not publish a partially validated current pointer.

## Persistence and compatibility

New captures use immutable `ProbablesAssessmentObservations`, schema `KRONOS-INTRADAY-ASSESSMENT-OBSERVATIONS` **1.1.0**, under `probables-v2/assessment-observations-v1/<run identity>.json`. Each row binds the exact run/result, canonical security, direction, phase, session, analysis boundary, source mapping and methodology. Run integrity and ordered exact admission membership are verified. Duplicate admission identities fail closed; repeated subjects across distinct runs remain distinct.

A positive `AdmissionMarketPriceProof` retains the exact Decimal representation of normalized Provider price, Provider observation time, operation identity, observation identity, normalized quote document and SHA-256 digest, exact Provider instrument identity, Sponsor policy identity, capture start/completion and proof integrity. The normalized document preserves the Provider contract payload; it is not represented as raw HTTP bytes. Observation identity binds operation/run/admission/source digest. Restoration verifies that the retained quote price, timestamp and instrument match the proof. Hashes prove integrity; the approved policy and governed producer binding establish authority.

`PRICE_NOT_RETAINED` requires null price/time/source/proof/derivation fields; zero is not missing data. Version **1.0.0** companions and the original `AdmissionPriceProof` retain their original pre-analysis-boundary validation unchanged. Direct historical/isolated persistence without the commissioned operation adapter remains missing; it never acquires a quote. The capture adapter always uses `EXACT_PRICE_PERSISTED`, never candle-derived classification.

Current pointers remain `AssessmentBoundProbablesV2Pointer` **2.1.0**, with exact companion identity. Legacy **2.0.0** pointers restore unchanged. Existing Probables run/result/mapping schemas and identities remain unchanged. An existing run is never recaptured or backfilled, including historical runs lacking companions. A retained pending companion after interrupted persistence is reused without another quote. Successful replay preserves all original bytes. Missing/tampered companion behind a bound pointer fails restoration; persistence failure preserves the previous current pointer.

## Truthful operation accounting

WO-05B accounting **1.1.0** adds `ASSESSMENT_OBSERVATION_REQUEST` to the four existing request categories. Each actual DOMAIN-006 quote invocation is counted once, including calls that raise or are refused by the lease. Physical HTTP attempts remain `NOT_RETAINED`; a lease/API attempt is not claimed to be a completed remote request. Existing request order and category meanings are unchanged. NIFTY quote invocation participates in the existing overlapping benchmark-subject count. Nominal coverage remains separate from actual requests. Measurement failure does not alter factual evaluability or Probables population.

Historical accounting **1.0.0** restores its original four categories byte-for-byte. Unknown historical counts stay unknown, known zero stays zero, and missing telemetry time cannot discard a known count or be fabricated by a later invocation. Operation completion/duration includes assessment capture. No extra Browser operational endpoint is introduced.

## Qualification and boundaries

Isolated tests prove exact same-quote pairing, after-analysis Provider time distinct from receipt, all phases and both directions, index/native/proxy binding, partial failure, no-admission behavior, pre-publication capture, replay without acquisition, interrupted persistence, immutable restoration, tamper rejection and version compatibility. Full composed 09:30 fixtures use real admission methodology and deterministic Provider doubles: first 15M and three 5M complete, forming current-day 1H excluded, prior completed 1H allowed. Trusted 09:29/requested 09:30 still rejects before acquisition. Methodology **2.2.0**, WO-06A Opening and WO-06B source binding remain unchanged.

Engineering qualification performs no production Provider/OpenAI/broker call, Refresh, live Probables generation, runtime restart or evidence mutation. Production rollout and real capture require separate authorization. Statistics, outcomes/EOD, WO-06D, CPR effectiveness research, VWAP, WO-10 and WO-18 remain held.
