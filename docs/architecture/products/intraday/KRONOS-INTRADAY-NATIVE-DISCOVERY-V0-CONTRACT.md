# KRONOS Intraday Native Discovery V0 Contract

**Status:** WO-03 review candidate

## 1. Governed identities

| Contract | Identity | Version |
|---|---|---|
| Native Discovery | `KRONOS-INTRADAY-NATIVE-DISCOVERY-V0` | `0.1.0` |
| Result | `KRONOS-INTRADAY-NATIVE-DISCOVERY-RESULT-V0` | `0.1.0` |
| Reason | `KRONOS-INTRADAY-NATIVE-DISCOVERY-REASON-V0` | `0.1.0` |
| Machine-fact bundle | `KRONOS-INTRADAY-NATIVE-DISCOVERY-MACHINE-FACT-BUNDLE-V0` | `0.1.0` |

The current binding is to `KRONOS-INTRADAY-NATIVE-UNIVERSE-V1 / 1.0.0`
and `KRONOS-INTRADAY-CANONICAL-RUNTIME-RECONCILIATION-V1 / 1.0.0`.
Each run records the exact identities, versions, integrity identities, market
session boundary, observation boundary, and included member identities.

## 2. Authority

Native Discovery owns deterministic factual evaluability, candidate-contract
state, bounded reasons, run/result identity, accounting, and immutable
persistence. It does not own Analytical Promotion, Trade Construction, Risk,
Entry Timing, lifecycle, Sponsor position, notification authority, execution
eligibility, or broker execution.

Native Discovery is not Analytical Promotion. The V0 contract contains no
`BUY NOW`, `SELL NOW`, `BUY READY`, `SELL READY`, `POTENTIAL`, `NO SETUP`,
KR-370, K1–K5, or Swing numerical policy.

## 3. Universe and factual operating scope

Every run accounts for the entire governed universe. Current factual scope is:

| Accounting field | Current value |
|---|---:|
| Universe members | 98 |
| Factually evaluable | 93 |
| Prerequisite unavailable | 5 |
| Evaluated by WO-03 | 0 |
| Candidate results produced by WO-03 | 0 |
| Other factual failures | 0 |

The 93-member factual subset is not a product universe. Membership remains 98.
WO-05 owns scanner execution and later candidate evaluation.

Current prerequisite-unavailable results are:

| Member | Reason |
|---|---|
| GOLDM | `ACTIVE_DERIVATIVE_BINDING_UNAVAILABLE` |
| SILVERM | `ACTIVE_DERIVATIVE_BINDING_UNAVAILABLE` |
| COPPER | `ACTIVE_DERIVATIVE_BINDING_UNAVAILABLE` |
| NATGAS | `PROVIDER_CONTRACT_UNAVAILABLE` |
| CRUDE | `PROVIDER_CONTRACT_UNAVAILABLE` |

`PREREQUISITE_UNAVAILABLE` is factual only. It is not candidate rejection,
`NO SETUP`, direction, weakness, trade quality, or execution ineligibility.
A successor governed reconciliation can make a member evaluable without a
universe or Discovery-contract redesign.

## 4. Result states

Evaluability states are:

- `FACTUALLY_EVALUABLE`;
- `PREREQUISITE_UNAVAILABLE`;
- `FACTUAL_FAILURE`; and
- `OTHER_GOVERNED_UNAVAILABLE`.

Candidate contract states are:

- `NOT_EVALUATED`;
- `CANDIDATE_ADMITTED`;
- `CANDIDATE_NOT_ADMITTED`;
- `NOT_EVALUATED_DUE_TO_PREREQUISITE`; and
- `NOT_EVALUATED_DUE_TO_FACTUAL_FAILURE`.

WO-03 does not populate admitted/not-admitted states from methodology. Those
typed states are contract seams for a later governed scanner. Every result
keeps execution eligibility `NOT_ESTABLISHED`.

## 5. Structural and completed-candle boundary

The structural timeframe family is exactly `1D / 1H / 15M / 5M`.
`1W` and `4H` are not authorized. Current ticks and incomplete candles are
observation only.

Only completed governed candles may enter structural authority. The bundle
fails closed when any mandatory structural timeframe is absent, incomplete,
stale, duplicated, or not reconciled against the governed session boundary.

## 6. Machine-fact eligibility bundle

Mandatory families are:

- DOMAIN-008 market/session boundary;
- governed completed OHLCV for all four structural timeframes; and
- completeness/reconciliation for all four structural timeframes.

Every bundle binds canonical identity, universe and reconciliation versions,
market/session boundary, observation boundary, evidence identities, fact
versions, source identities, provenance, and deterministic integrity.

Available but optional/telemetry-only families are previous-session facts,
PDH/PDL, Classic Pivots, CPR, structural comparisons, local pivots/barriers,
touch/break/close/retest, range/move/retracement, volume observations,
reference distance, structural R:R, and session-position observations.
Availability creates no candidate consequence.

## 7. Methodology deferrals

ATR, SMA20/50/200, relative-volume consequence and lookback, volume threshold,
normalized extension, path-clearance arithmetic/consequence, nearest-barrier
selection, directional admission, candidate thresholds, and weighted scoring
remain `DEFERRED_PENDING_EVIDENCE`.

Session-position telemetry is `NOT_REQUIRED_NOW`: DOMAIN-008 session truth is
mandatory, but WO-03 creates no time-based candidate or execution consequence.
The future product new-entry clocks remain separate from market truth.

## 8. Persistence and history

Runs and member results use deterministic canonical serialization, immutable
atomic writes, explicit identity reads, idempotent identical retention,
conflicting duplicate rejection, integrity validation, and restart-safe
reconstruction. There is no latest-filename authority. A later run never
mutates historical evidence.

## 9. Slice 3V and Browser

Slice 3V is independent validation evidence. Chart or visual Answers cannot
alter machine candidate state or replace machine facts. Browser remains a
derivative projection and performs no Discovery calculation.

## 10. WO-04 decision

No mandatory factual family in this non-threshold V0 contract is missing.
Therefore:

`WO-04 REQUIRED = NO`

Current factual foundations are sufficient for WO-05 implementation of this
contract. This decision does not close the deferred methodology decisions.
