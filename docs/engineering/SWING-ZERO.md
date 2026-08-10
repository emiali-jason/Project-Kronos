# Swing Zero

## Status

**VALIDATED EXECUTABLE BASELINE**

Validation baseline: **2026-08-10**

Swing Zero is the first executable deterministic Swing classification baseline.
It consumes validated, completed Provider Foundation V2 Daily candles and
independently evaluates exactly two setup families: Pullback Continuation and
Consolidation Breakout.

## Product Boundary

Input: an ordered sequence of validated, completed, provider-neutral Daily
candles and its `HistoricalCandleRequest`.

Output: two immutable `SwingAssessment` objects, one for each setup family.

Swing Zero provides no:

- ranking or winner selection;
- action confirmation;
- COMEX or reference confirmation;
- execution or order capability;
- portfolio logic;
- confidence scoring; or
- third setup family.

## Policy Identity

`SWING-ZERO-V0-CLASSIFICATION-POLICY`

The frozen parameters are:

- SMA period: 20 completed Daily closes;
- SMA slope comparison: SMA20 five completed bars earlier;
- pullback window: five completed Daily bars;
- ATR period: 14 bars;
- consolidation window: ten completed Daily bars;
- consolidation threshold: Range Width ≤ 2.5 × ATR14;
- continuation trigger: completed close beyond the previous-day high or low;
- breakout trigger: completed close beyond the preceding range;
- minimum lookback: 25 completed Daily candles;
- volume has no classification authority; and
- there is no independent volatility gate.

## Trend Rules

- **BULLISH:** current Close > current SMA20 and current SMA20 > SMA20 five
  completed bars earlier.
- **BEARISH:** current Close < current SMA20 and current SMA20 < SMA20 five
  completed bars earlier.
- **NEUTRAL:** neither bullish nor bearish predicate is satisfied.

## Pullback Continuation

An orderly bullish pullback requires at least one lower close in the five-bar
window and no close below its corresponding SMA20. The bearish rule mirrors
this: at least one higher close and no close above its corresponding SMA20.

- **NO_SETUP:** the frozen trend and orderly-pullback predicates are not
  satisfied.
- **FORMING LONG:** bullish trend plus a current orderly bullish pullback,
  without completed continuation confirmation.
- **FORMING SHORT:** bearish trend plus a current orderly bearish pullback,
  without completed continuation confirmation.
- **QUALIFIED LONG:** bullish trend remains valid, the *preceding* five-bar
  window is an orderly bullish pullback, and the current completed close is
  above the previous-day high.
- **QUALIFIED SHORT:** bearish trend remains valid, the *preceding* five-bar
  window is an orderly bearish pullback, and the current completed close is
  below the previous-day low.

For qualification, the current completed candle is confirmation and is not
part of the preceding five-bar pullback window.

## Consolidation Breakout

The consolidation window is the previous ten completed Daily candles,
excluding the current candle. Range High and Range Low are the maximum high and
minimum low in that window. ATR14 is evaluated at the end of the preceding
candle. Consolidation exists when Range Width ≤ 2.5 × ATR14.

- **NO_SETUP:** the preceding range is not a frozen-policy consolidation.
- **FORMING:** consolidation exists and the current completed close remains
  within the range.
- **QUALIFIED LONG:** consolidation exists and the current completed close is
  above Range High.
- **QUALIFIED SHORT:** consolidation exists and the current completed close is
  below Range Low.

Intraday high or low penetration without a completed close outside the range
does not qualify a breakout. The current candle cannot change the preceding
range or the ATR14 used to determine consolidation.

## SwingAssessment

`SwingAssessment` is an immutable, frozen, slotted value object containing:

- `instrument`;
- `observation_boundary`;
- `rule_set_version`;
- `direction`;
- `setup`;
- `state`;
- `why`;
- `evidence_for`;
- `evidence_against_or_risks`;
- `entry_zone`;
- `invalidation`;
- `stop`;
- `targets`;
- `risk_reward`; and
- `next_required_event`.

The setup families are evaluated independently. Both may qualify on the same
observation boundary; Swing Zero performs no ranking or suppression.

Trade-plan fields (`entry_zone`, `invalidation`, `stop`, `targets`, and
`risk_reward`) remain absent because Swing Zero has no frozen Trade Plan
policy.

## Fail-Closed Rules

The following produce typed analysis failures rather than `NO_SETUP`:

- fewer than 25 completed Daily candles;
- a non-Daily request;
- duplicate or non-monotonic observation boundaries;
- malformed OHLC structure;
- non-finite or invalid numeric values;
- incomplete observations where completion state is represented;
- unavailable or invalid data quality where quality state is represented; and
- malformed or inconsistent provider-neutral observations.

## Provider Boundary

Swing Zero consumes Provider Foundation V2 contracts and normalized output.
Provider-private instrument identity remains inside Provider Foundation V2.
Swing Zero does not authenticate, construct a Kite client, or communicate
directly with Kite.

Production implementation:

- `src/kronos/swing/__init__.py`
- `src/kronos/swing/zero.py`

Tests:

- `tests/unit/swing/test_swing_zero.py`

## Validation

Offline validation:

- focused Swing Zero tests: **35 passed**;
- complete offline regression: **1013 passed**;
- deterministic repeatability: **PASS**; and
- immutability: **PASS**.

Real Phase-1 validation used 85 completed Daily candles for each resolved
nearest unexpired MCX future and excluded the current incomplete trading day:

| Instrument | Pullback Continuation | Consolidation Breakout |
| --- | --- | --- |
| GOLDM | NO_SETUP | NO_SETUP |
| SILVERM | NO_SETUP | NO_SETUP |
| COPPER | FORMING LONG | NO_SETUP |

Independent engineering sanity calculations matched the published engine
evidence for all three instruments.

Swing Zero validation proves deterministic implementation correctness against
real Phase-1 data. It does **not** prove profitability or parameter optimality.

## Change Rule

Do not tune V0 parameters in response to one real observation. Any future rule
or parameter change requires explicit evidence and a new policy/version; it
must not silently alter `SWING-ZERO-V0-CLASSIFICATION-POLICY`.

## Deferred Scope

- ranking and Top 0–2 selection;
- the full Swing Phase 1 universe;
- Trade Plan policy;
- browser workspace;
- LIVE, PAPER, and IGNORE decisions;
- Entry Thesis monitoring;
- WebSocket active-trade monitoring;
- exit and journal behavior;
- COMEX or reference confirmation; and
- execution.
