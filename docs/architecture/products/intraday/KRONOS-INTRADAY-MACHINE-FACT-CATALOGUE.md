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
| `NARROW_CPR_KGS_V0` | AVAILABLE_DETERMINISTIC_FACT | Previous completed 1D H/L/C; strict factual compression classification only |
| Narrow CPR → Probable consequence | QUALIFICATION_REQUIRED | Market usefulness and admission consequence are not established |
| Nearest-barrier selection authority | BARRIER_SELECTION_METHODOLOGY_REQUIRED | Known distances are factual; nearest/important selection requires evidence and CA authority |
| ATR | NOT_REQUIRED_FOR_CURRENT_METHODOLOGY_RESEARCH | Existing range/move facts support Part-2 representation; future need, period and consequence remain deferred |
| SMA20/50/200 | NOT_REQUIRED_FOR_CURRENT_METHODOLOGY_RESEARCH | Part-2 hypotheses are representable without importing Swing SMA methodology |
| Relative-volume consequence | DEFERRED_METHODOLOGY | Volume remains telemetry |
| Path-clearance consequence | DEFERRED_METHODOLOGY | Threshold remains deferred |
| Extension consequence | DEFERRED_METHODOLOGY | Threshold remains deferred |
| Directional admission | DEFERRED_METHODOLOGY | WO-06 evidence required; no Long/Short consequence |
| Candidate scoring/ranking | DEFERRED_METHODOLOGY | No score, quota, ranking or top-N is commissioned |
| Additional failed-break/pivot sequencing | DEFERRED_METHODOLOGY | Validate factual need first |
| Historical completed 1D/1H/15M/5M reconstruction | OPERATIONAL_SEAM_AVAILABLE_REAL_EVIDENCE_PENDING | Research-only, explicit completed-session EOD boundary, bounded Provider reads and no look-ahead; production Discovery identity is not reused |
| Historical previous-session H/L/C, CPR and Narrow CPR | OPERATIONAL_SEAM_AVAILABLE_REAL_EVIDENCE_PENDING | DOMAIN-008 previous trading session and unchanged `NARROW_CPR_KGS_V0`; no Probable consequence |
| Historical canonical/Provider subject binding | FAIL_CLOSED_EXACT_IDENTITY | No fuzzy match or current-symbol substitution; unresolved subjects remain unavailable |
| Historical MCX derivative contract | HISTORICAL_PREREQUISITE_UNAVAILABLE | Exact contract identity required; no active/front/nearest/liquidity/OI selection |

No `MISSING_REQUIRED_FOR_DISCOVERY` fact was found for the approved
non-threshold V0 contract. WO-04 is therefore skippable. This does not convert
deferred methodology into authority.

WO-06 Part 2 found no machine-fact enhancement required to implement the
research framework. Real evidence may still establish a precise later gap.

WO-06HA closes the engineering seam with a completed-session EOD boundary,
pre-acquisition request ceiling and explicit invocation. It performs no real
acquisition and grants no methodology or production authority.
