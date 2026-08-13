# KRONOS Swing V1 Slice 3 — TradingView Context Intake

- **Authority:** Slice 3 authorized
- **V0:** frozen and unchanged
- **Retention policy:** `KRONOS-V1-EVIDENCE-RETENTION-POLICY-CANDIDATE`
- **Pruning:** manual only
- **Durable root:** `~/Library/Application Support/KRONOS/evidence/swing-v1`

## Implemented Boundary

Slice 3 converts probable setup assessments into one run-scoped TradingView
review requirement per unique instrument. Each requirement retains the run,
completed observation boundary, instrument, every probable setup/direction
identity, explicit timeframe set, chart template identity, and context status.
Only `PROBABLE_CANDIDATE` assessments create requirements; there is no Top-2 or
other truncation.

Daily is required by invariant. Supporting 4H and 1H charts are available only
when explicitly configured by the context policy. The Browser identifies the
upload slot before intake. It accepts PNG, JPEG, or WebP bytes and does not infer
instrument or timeframe from a filename.

## Evidence and Gate

The original chart is written unchanged using an atomic replace. SHA-256,
byte count, MIME type, upload timestamp, source, retention class, template,
boundary, run and instrument are retained in an atomic manifest. An exact
duplicate for the same timeframe is rejected; a changed replacement becomes a
new immutable revision.

The context gate permits these states only:

1. `TRADINGVIEW_REVIEW_REQUIRED` — no required chart received;
2. `CONTEXT_INCOMPLETE` — some but not all required charts received; and
3. `TRADINGVIEW_CONTEXT_RECEIVED` — every required chart slot retained.

No state grants Readiness, Trade Construction, R:R, ranking or execution
authority. Automated visual extraction is deferred because no approved
deterministic image-to-structured-evidence boundary exists.

## SMA and Structured Evidence

Layer 1 retains machine-derived SMA20 facts only as a required input; it does
not expand Provider history to make SMA50 or SMA200 required. Layer 2 supports
visual SMA20, SMA50 and SMA200 evidence by semantic indicator identity,
timeframe and template version. Current red/white SMA50/SMA200 colours are
cosmetic metadata, not identity. A same-boundary material SMA20 disagreement is
represented as `DATA_ALIGNMENT_REVIEW`.

Structured evidence keeps price structure, each moving average, CPR/previous
day/week levels, visible structural support/resistance, candle behaviour, Pine
display and contradictions separate, with availability and provenance. There
is no generic TradingView score and Pine never overrides the core.
