# KRONOS Intraday WO-12 K5 Fact Foundation V1

Status: FACTUAL FOUNDATION / RESEARCH-ONLY OUTCOME CONTRACT

Version: 1.0.0

The K5 material-extension threshold remains `POLICY_UNRESOLVED`. This contract
does not make a WO-12 promotion decision and is not wired into production
runtime composition.

## Contract identities

- Structural origin: `KRONOS-INTRADAY-WO12-15M-STRUCTURAL-ORIGIN-V1`
- ATR: `KRONOS-INTRADAY-15M-WILDER-RMA-ATR-14-V1`
- Forward outcome: `KRONOS-INTRADAY-WO12-15M-FORWARD-STRUCTURE-OUTCOME-V1`
- Forward authority: `RESEARCH_ONLY_NO_PRODUCTION_ANALYTICAL_AUTHORITY`

## Structural origin

The origin is bound only from governed 15-minute structural evidence whose
confirmation boundary is at or before the analysis boundary.

For `INTRADAY_PULLBACK_CONTINUATION`, the origin is the start of exactly one
direction-aligned `DIRECTIONAL_MOVE_MEASUREMENT` produced by
`EXPLICIT_DIRECTIONAL_MOVE_MEASUREMENT_V1`:

- LONG uses `move_start_low`.
- SHORT uses `move_start_high`.

For `INTRADAY_RANGE_BREAKOUT`, the origin is the directional boundary of one
explicit governed range with at least one matching direction-aligned explicit
range-break fact:

- LONG uses `range_high` with `BOUNDARY_BREAK_ABOVE`.
- SHORT uses `range_low` with `BOUNDARY_BREAK_BELOW`.

Multiple break events for the same uniquely identified range preserve their
lineage and do not change the range origin. Multiple qualifying move identities,
multiple qualifying range identities, missing values, non-15-minute evidence,
or boundary mismatch produce `UNAVAILABLE`. Candidate local pivots and
arbitrary lookback windows have no origin authority.

## Completed-candle ATR

ATR uses completed governed 15-minute candles only. True Range is:

`max(high - low, abs(high - previous_close), abs(low - previous_close))`

The first ATR is the arithmetic mean of the first 14 True Range values.
Subsequent values use Wilder/RMA:

`ATR = ((previous_ATR * 13) + current_TR) / 14`

Fewer than 14 completed candles, a non-positive result, a held MCX subject, or
an MCX contract-roll crossing produces `UNAVAILABLE`. The retained candle and
actual-contract lineage remains in the fact. No Provider acquisition occurs.

## Research-only forward outcome

The forward contract evaluates 4, 8, and 12 completed 15-minute bars as three
separate horizons. It starts strictly after the original analysis boundary and
requires contiguous candles in the same governed market session. MCX evidence
must remain within one actual derivative contract. Closed-session gaps and
contract rolls are not bridged.

At each terminal boundary, exactly one governed available
`15M_STRUCTURE` semantic fact supplies the outcome:

- direction aligned with the inherited thesis: `CONTINUED`;
- opposite LONG/SHORT direction: `FAILED`;
- non-directional or conflicting structure: `INDETERMINATE`.

Missing or ambiguous terminal structure is unavailable and retains
`INDETERMINATE` as the non-consequential label. No price-return percentage,
P&L, Sponsor outcome, execution, or broker evidence is used.

## MCX boundary

MCX inputs are actual-contract local and never span a roll. NATGAS remains
held. COMEX/NYMEX reference evidence and USDINR evidence do not establish K5
origin, ATR, or outcome.

## Frozen K5 arithmetic

The existing formula is unchanged:

- LONG: `(completed_close - structural_origin) / ATR`
- SHORT: `(structural_origin - completed_close) / ATR`

These facts can populate the existing measurement contract. They cannot turn
K5 into `SATISFIED` or `UNSATISFIED` while the material-extension threshold is
unresolved.

## Qualification-corpus audit

The read-only audit of qualification corpus
`INTRADAY-QUALIFICATION-CORPUS-f70fadc6b256f3e6d5424598228c73e352684e2e789ba328de56c69f0cf5029f`
found:

- observations considered: 465;
- structural origin available: 0;
- ATR-14 available: 465;
- 4-bar forward outcome available: 0;
- 8-bar forward outcome available: 0;
- 12-bar forward outcome available: 0;
- fully qualified at each horizon: 0.

The retained candles are sufficient for ATR reconstruction. The corpus does not
retain a governed setup-family-to-explicit-move/range origin binding, and its
end-of-session observation boundaries do not retain same-session future
4/8/12-bar terminal structure. No data was fetched to fill those gaps.
