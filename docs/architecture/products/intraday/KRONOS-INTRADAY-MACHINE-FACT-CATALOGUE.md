# Intraday Machine-Fact Catalogue and Gap Register

**Status:** WO-03 gap audit; no numerical thresholds

| Fact family | Status | Boundary |
|---|---|---|
| Governed 1D/1H/15m/5m OHLCV | AVAILABLE | Mandatory completed governed candle facts |
| Completed-candle reconciliation | AVAILABLE | Mandatory DOMAIN-008 schedule-aware publication |
| Market/session boundary | AVAILABLE | Mandatory DOMAIN-008 factual boundary |
| Previous-session H/L/C and PDH/PDL | AVAILABLE_BUT_TELEMETRY_ONLY | No admission consequence |
| Classic Pivots and CPR | AVAILABLE_BUT_TELEMETRY_ONLY | Factual context only |
| Structural comparisons | AVAILABLE_BUT_TELEMETRY_ONLY | Factual comparisons only |
| Local structural pivots/barriers | AVAILABLE_BUT_TELEMETRY_ONLY | No selection consequence |
| Touch/break/close/retest facts | AVAILABLE_BUT_TELEMETRY_ONLY | No admission consequence |
| Range/move/retracement measurements | AVAILABLE_BUT_TELEMETRY_ONLY | Explicit-input arithmetic |
| Volume comparisons | AVAILABLE_BUT_TELEMETRY_ONLY | Shadow/factual telemetry |
| Reference distance and structural R:R telemetry | AVAILABLE_BUT_TELEMETRY_ONLY | No consequence |
| Session-position observations | AVAILABLE_BUT_TELEMETRY_ONLY | Not required by V0 admission contract |
| Current/incomplete candle | AVAILABLE_BUT_TELEMETRY_ONLY | Observation only; structural consequence prohibited |
| Nearest-barrier selection authority | DEFERRED_METHODOLOGY | Requires evidence and CA authority |
| ATR | DEFERRED_METHODOLOGY | Period and consequence remain deferred |
| SMA20/50/200 | DEFERRED_METHODOLOGY | Need and use remain unproven |
| Relative-volume consequence | DEFERRED_METHODOLOGY | Volume remains telemetry |
| Path-clearance consequence | DEFERRED_METHODOLOGY | Threshold remains deferred |
| Extension consequence | DEFERRED_METHODOLOGY | Threshold remains deferred |
| Additional failed-break/pivot sequencing | DEFERRED_METHODOLOGY | Validate factual need first |

No `MISSING_REQUIRED_FOR_DISCOVERY` fact was found for the approved
non-threshold V0 contract. WO-04 is therefore skippable. This does not convert
deferred methodology into authority.
