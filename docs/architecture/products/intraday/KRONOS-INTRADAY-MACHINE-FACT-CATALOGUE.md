# Intraday Machine-Fact Catalogue and Gap Register

**Status:** WO-03A controlled record; no numerical thresholds

| Fact family | Status | Boundary |
|---|---|---|
| Governed 1D/1H/15m/5m OHLCV | AVAILABLE | Completed governed candle facts |
| Completed-candle reconciliation | AVAILABLE | DOMAIN-008 schedule-aware publication |
| Previous-session H/L/C and PDH/PDL | AVAILABLE | Previous governed trading session |
| Classic Pivots and CPR | AVAILABLE | Factual context only |
| Structural comparisons | AVAILABLE | Factual comparisons only |
| Local structural pivots/barriers | AVAILABLE | Factual structure foundation |
| Touch/break/close/retest facts | AVAILABLE | No trading consequence |
| Range/move/retracement measurements | AVAILABLE | Explicit-input arithmetic |
| Volume comparisons | AVAILABLE | Shadow/factual telemetry |
| Reference distance and structural R:R telemetry | AVAILABLE | Only where inputs are explicit; no consequence |
| Session-position telemetry | CONTRACT_NOW | Contract factual position without threshold |
| Nearest-barrier selection authority | WAIT_NATIVE_DISCOVERY | Requires Discovery evidence and authority |
| ATR | WAIT_NATIVE_DISCOVERY | Period and consequence are deferred |
| SMA20/50/200 | WAIT_NATIVE_DISCOVERY | Need and use are not yet evidenced |
| Relative-volume consequence | WAIT_3V | Observe first; no consequence frozen |
| Path-clearance consequence | WAIT_NATIVE_DISCOVERY | Threshold deferred |
| Extension consequence | WAIT_NATIVE_DISCOVERY | Threshold deferred |
| Additional failed-break/pivot sequencing | WAIT_3V | Validate factual need first |

`NOT_REQUIRED_V1` is retained as a valid classification for proposed facts
shown by evidence to be unnecessary. No current fact is assigned that outcome
without evidence.
