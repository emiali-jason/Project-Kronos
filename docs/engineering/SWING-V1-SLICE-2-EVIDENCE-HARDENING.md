# KRONOS Swing V1 Slice 2 Evidence Hardening

## Scope

Slice 2 completes Layer-1 evidence and reconciliation contracts. It introduces
no TradingView ingestion, Readiness, trade construction, R:R, ranking, Browser
workflow, or execution authority. V0 remains frozen.

## Semantic States

- `POLICY_UNRESOLVED` means the required facts exist but approved deterministic
  policy is insufficient.
- `EVIDENCE_INCOMPLETE` means required facts are missing.
- `UNAVAILABLE` and `NOT_APPLICABLE` remain evidence-availability states rather
  than probable classifications.
- Only `PROBABLE_CANDIDATE` reconciles to `READY_FOR_CONTEXT` and receives
  `TRADINGVIEW_CONTEXT_PENDING`.

`POLICY_UNRESOLVED` has a distinct reconciliation state and is never mapped to
`EVIDENCE_INCOMPLETE`.

The exact same-98 regression intentionally changes the state split from
`POLICY_UNRESOLVED=110 / EVIDENCE_INCOMPLETE=0` to
`POLICY_UNRESOLVED=104 / EVIDENCE_INCOMPLETE=6`. RBLBANK, HDFCBANK, and IDEA
each have a complete radius-1 alternative but an unavailable radius-2
alternative for both setup families. Missing one required alternative is now
truthfully incomplete; disagreement between two available alternatives remains
policy unresolved. Probable and Not-Supported counts remain 5 and 81.

## Structural Alternatives

Radius-1 and radius-2 unique-extreme pivot definitions remain separately
identified. Their exact pivots, timestamps, values, definition identities, and
agreement/disagreement state are retained. No production pivot definition is
selected while that policy remains unfrozen.

## ETERNAL Impulse Tie Reference

The preserved ETERNAL boundary contains two equal maximum-range impulse
candidates:

| Candidate index | Direction | Range/ATR |
|---:|---|---:|
| 15 | SHORT | 1.5976886962802477 |
| 19 | LONG | 1.5976886962802477 |

The existing deterministic selection policy,
`MAX_RANGE_ATR_THEN_EARLIEST_INDEX`, selects index 15. The selected SHORT
candidate does not align with the bullish structural hypothesis, so the
Pullback assessment remains `NOT_SUPPORTED`. Both candidates and the exact tie
are retained, and the architectural question is recorded separately as
`IMPULSE_TIE_POLICY_REVIEW`. Slice 2 does not replace or tune the tie-break.

## Moving-Average History

Moving-average availability is component-specific; there is no generic MA
availability field. Current requirements are explicit:

- SMA20 trend-quality evidence: 25 completed candles;
- SMA50 value and five-bar direction: 55 completed candles; and
- SMA200 context: 200 completed candles.

The current 30-candle dataset therefore supplies SMA20 and truthfully marks
SMA50/SMA200 unavailable. Slice 2 does not expand Provider retrieval.

## Measurement Versus Policy

Volume retains current, normal mean/median, setup-comparison mean, normalized
ratios, and the comparison role. `POLICY_UNRESOLVED_NO_THRESHOLD` explicitly
separates those measurements from any future "increase" or "sizeable" rule.

Volatility retains ATR-normalized range, NR4/NR7, inside-day, percentile,
short/long, pre-break and breakout measurements. Its role is supporting for
Pullback and setup-quality for Breakout, with no directional authority.

Candles retain numerical morphology and contextual acceptance, rejection,
indecision, contraction/expansion and close-back-inside labels. Named patterns
have no trade authority.

## Futures OI Dependency

The approved vocabulary is retained: `LONG_BUILDUP`, `SHORT_BUILDUP`,
`SHORT_COVERING`, and `LONG_UNWINDING`. Interpretation is unavailable unless
the facts are proven roll-normalized. Trusted future evidence requires current
contract identity, expiry, a comparable roll-adjusted OI series, and continuity
across contract roll. Current MCX assessments remain unavailable with explicit
OI policy and roll-normalization reasons.

## Relative and Gap Context

Only READY equity benchmark relationships are admitted. KAYNES remains REVIEW;
commodities receive no invented benchmark. Relative context remains supporting
and has no veto authority. Gap evidence remains objective, has no news-causation
claim, creates no standalone setup, and has no automatic veto.
