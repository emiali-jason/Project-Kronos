# NSE local quantitative research — method 1.0

LOCAL-01 isolated implementation, 18 October 2026. Method identity:
`KRONOS-NSE-LOCAL-RESEARCH-1.0`. This is an explainable research heuristic,
not a calibrated forecast, accepted visual Answer, Native decision or trading plan.
No production integration is included in this slice.

## Existing authority and reuse

The engine consumes the existing eligible NSE Native Review requirement,
Native discovery record and same-run completed MTF snapshot. It does not scan
another universe, rerun Native or call a Provider. The unchanged SW-FAST-02
`nse_technical_summary.py` and its owning tests are ported from the frozen
unshipped candidate. Its factual comparisons and Q3/Q5/Q10 UNKNOWN semantics
are preserved. The API-independent SW-FAST-03 input checks and arithmetic
principles are salvaged; its model operation, prompt, transport, workflow,
response schema and API-constrained scenario prohibition are not dependencies.

Completed candles, SMA20/50/200, five-bar-prior SMA, prior20 volume reference,
radius1/radius2 pivots and completed1H arithmetic ATR14 remain their existing
owners' facts. No new indicator owner is introduced. Full-history checks are
validation of supplied facts, not replacement values or a second calculation
authority. Missing owner facts are never filled by this validator.

## Public interface and immutable contracts

`build_local_input(requirement, native, facts, publication_sha256)` creates
`LocalAnalysisInput`. `validate_input()` and duplicate-key-rejecting
`decode_input()` validate the closed `KRONOS-SWING-NSE-LOCAL-INPUT-V1`, version1.0.
The body holds binding, information cutoff, Native capture/observation time,
unchanged factual summary, Native thesis, four timeframe facts, complete consumed
historical bars and optional typed1H ATR.

`analyze_local(input, expected_source=SourceBinding(...))` returns frozen
`LocalAnalysisResult`, contract `KRONOS-SWING-NSE-LOCAL-RESULT-V1`, version1.0.
Both records serialize as canonical UTF-8 JSON (sorted keys, compact separators,
no NaN/Infinity). Their identities are SHA-256 of the complete canonical body.
`validate_result()` and `decode_result()` independently derive and compare the
entire result, including source citations, parameters, opinion and geometry.

`SourceBinding` includes input hash, run, publication, exact instrument, Native
assessment hash, Review requirement hash, Provider fact identity and cutoff.
The canonical caller must independently obtain this expected binding and apply
its existing final-currentness fence before retention/display. Passing the input's
own binding is suitable for a labelled synthetic demonstration; it cannot certify
production currentness. A self-consistent hash does not authenticate fabricated
external evidence. LOCAL-01 neither reads a production store nor certifies market
sessions, freshness, current quotations or live admissibility.

The complete consumed history is included because the existing MTF owner identity
does not itself hash every historical NSE bar. Any earlier-bar change changes the
local input hash even if the latest owner identity is unchanged. Older snapshots
that retain only their latest bar remain valid but cannot establish five-bar price
momentum. Inputs are bounded to16MiB and10,000bars per timeframe.

Validation requires exact four-frame order1W/1D/4H/1H, owner round trips, exact
requirement construction, current snapshot/Native bindings, aware source clocks,
completed boundaries no later than cutoff, strictly ordered history and exact
latest-bar agreement. ATR retains its separate analytical anchor: it may precede
the latest1H completion under the canonical producer, but cannot exceed cutoff.
Its instrument/run, completed observation, data boundary, calendar/session/provider
and integrity remain exact. No new exchange calendar semantics are inferred.

When sufficient exact history exists, supplied non-null SMA/current-prior values,
prior20 volume and arithmetic ATR14 must agree with their owner formulas. With a
shorter historical window the result preserves typed owner facts without claiming
that this validation independently reconstructed them. Null owner values remain
null even if raw bars could calculate a number.

## Numerical semantics

- Close/reference distance: `100 * (close - reference) / reference`.
- Five-bar SMA change: `100 * (SMA_now - SMA_prior5) / SMA_prior5`.
- Price momentum: `100 * (last_close - close_5bars_ago) / close_5bars_ago`;
  six retained completed bars are required.
- Participation: current volume divided by the existing preceding20-bar mean,
  excluding current volume. Participation is not directional confirmation.
- Candle body: `100 * (close - open) / open`; range: `100*(high-low)/close`.
- Pivot proximity: signed close-to-pivot percent, with exact observed pivot
  value, timestamp and window-relative candle index retained.
- ATR distance: `(close - reference) / completed1H_ATR14`, only for1H. Existing
  ATR is the arithmetic mean of14 true ranges from15 completed1H bars; it is not
  Wilder smoothing. No hourly-to-daily/weekly volatility conversion is made.

Missing, zero or nonpositive denominators produce UNAVAILABLE with an explicit
reason. Invalid/nonfinite supplied evidence is rejected, not disguised as missing.
Every citation resolves through `source_references` to a JSON pointer and exact
value in the immutable input. This index is not an additional source of authority.

## Independent evidence and horizons

Each timeframe examines three domains, each contributing at most one signed vote:

1. Trend compares close/SMA20, close/SMA50 and SMA20/SMA50; at least two net signed
   agreements are required for a direction. SMA200 remains longer-trend context
   and a recorded contradiction where opposing; it is not a duplicated vote.
2. Momentum requires five-bar price return and the net sign of available five-bar
   SMA changes to agree. Missing either input is UNKNOWN; disagreement is NEUTRAL.
3. Structure compares the last two confirmed highs and lows for each existing
   radius separately. Both rising supports LONG; both falling supports SHORT;
   mixed/equal is NEUTRAL. Radius disagreement remains visible and withholds the
   structure vote. Missing pivots remain UNKNOWN.

A completed close below a bullish sequence's latest low, or above a bearish
sequence's latest high, neutralizes that structure and records the breach. It
does not infer a new opposite trend. A frame conclusion that still endorses the
breached sequence is vetoed; independent opposite trend/momentum may still stand.
Equality is reported without inventing a breach.

At least two available domains and net vote magnitude2 are needed for a frame
direction. Candle, volume and ATR context do not add correlated votes. Domain,
radius, candle, SMA200 and excessive1H extension contradictions remain explicit.

| Horizon | Research holding band | Required timeframe agreement | Scenario frame |
|---|---|---|---|
| SHORT |1–3 trading sessions|4H and1H|1H|
| MEDIUM |4–10 trading sessions|1D and4H|4H|
| LONGER |11–20 trading sessions|1W and1D|1D|

Both frames must agree. Missing produces UNKNOWN; mixed directions produce
NEUTRAL. These bands do not modify existing WO-12 checkpoints1/3/5/10 and do not
assert validated holding periods or20-session outcomes.

The overall medium-horizon anchor yields SUPPORT or CHALLENGE relative to Native;
all three horizons opposing Native yields REJECT; mixed/unavailable medium yields
WAIT; all horizons unknown yields INSUFFICIENT_EVIDENCE. Both LONG and SHORT
hypotheses remain present even when the overall opinion is neutral. HIGH/MODERATE/
LOW/UNAVAILABLE conviction reports coverage and agreement, never a win probability.
HIGH requires all horizons aligned, all domains available and no contradictions.

## Sourced conditional scenarios

The engine examines four styles × two directions × three horizons × both pivot
radii. Radius alternatives are not independent confirmations. Each scenario is
AVAILABLE geometry or UNAVAILABLE with a reason and null levels/R:R.

For LONG, supportive observed lows lie below the reference close and opposing
observed highs ahead; SHORT reverses these relations. Levels are deduplicated
by price while preserving all source coordinates. Invalidation is an exact
observed protective pivot, not an invented order buffer.

- IMMEDIATE anchors to the last completed close with a favorable-side entry
  interval. It does not mean BUY_NOW/SELL_NOW or that today's price is there.
- PULLBACK anchors to the nearest supportive pivot, using the next distinct
  protective pivot as invalidation. A future retest/hold remains unestablished.
- BREAKOUT anchors to the nearest opposing pivot ahead. A future completed
  break and retest is required; the trigger itself is not also its target.
- ALTERNATIVE examines the nonaligned directional hypothesis with a structural
  break/retest and failure of the opposite hypothesis; no activation is inferred.

Entry width is the minimum of10% of anchor-to-invalidation distance and25% of
the same-timeframe latest completed range. For1H only, it is also capped at25%
of positive completed1H ATR. Those fractions are explicit initial research
parameters, not market-calibrated optimal thresholds.1H immediate hypotheses
with absolute close/SMA20 extension above2ATR are withheld. Other horizons use
their own completed ranges and do not claim an unavailable same-timeframe ATR.

Targets are the nearest exact observed opposing pivot beyond the entire entry
interval. The target zone is explicitly degenerate at that sourced price: no
projected extension or target buffer is invented. No forward observed pivot means
no target and the entire scenario is withheld.

All entry endpoints must have positive signed risk/reward. Conservative R:R is
minimum reward across the entry interval divided by maximum risk. Below1 is
WATCH_GEOMETRY, not a claim of attractiveness. Ranking is by conservative geometry
only within a fixed horizon/direction/radius; it does not rank expected return,
fill likelihood or activation probability. Stops/targets are research references,
not exchange-tick-normalized orders. Fees, slippage, fills and realized P&L remain
unavailable. All scenarios require future independent price/currentness checks.

## Preservation, qualification and next boundary

Native/KR-370/K4/V2, accepted Answers, WO-07F, WO-12, Intraday, Theta, Browser,
Provider and lifecycle code remain byte-identical. Q3/Q5/Q10 stay UNKNOWN. Existing
shared Chart Analyst functionality is retained; the unshipped API-centric WO-08
product/release path is held and no historical artifact is deleted.

Tests run through the unchanged mandatory kernel-isolated harness, with actual
exits, failed attempts and source-before/source-after identities retained outside
source. Owning cases exercise symmetry/disagreement, missingness, current-source
mismatch, malformed/rehashed evidence, exact history consistency, structural
breaches, future boundaries, whole-zone R:R, immutable replay, citation resolution
and denied file/network/subprocess access. Affected owner cases protect existing
MTF, Native/Review/readiness/construction, V2 and WO-12 behavior. No fixed pass-count
or performance target substitutes for these assertions.

The demonstration uses labelled synthetic fixtures only. LOCAL-02 must add the
existing-owner post-commit/manual wiring, deduplication, immutable storage and
source/currentness-fenced Opportunities/Review projections. LOCAL-03 owns daily
recording and WO-12 workbook linkage; LOCAL-04 owns prospective measurement.
Release A/B and actual operational acceptance require separate authorization.
