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
| Narrow CPR → Probable consequence | V0_ADMISSION_SUPPORT_REQUIRED | WO-06 Part 3 freezes TRUE as required admission support from Variant-G population evidence; it supplies no direction, rank, outcome or performance claim |
| Nearest-barrier selection authority | BARRIER_SELECTION_METHODOLOGY_REQUIRED | Known distances are factual; nearest/important selection requires evidence and CA authority |
| ATR | NOT_REQUIRED_FOR_CURRENT_METHODOLOGY_RESEARCH | Existing range/move facts support Part-2 representation; future need, period and consequence remain deferred |
| SMA20/50/200 | NOT_REQUIRED_FOR_CURRENT_METHODOLOGY_RESEARCH | Part-2 hypotheses are representable without importing Swing SMA methodology |
| Relative-volume consequence | V0_SUPPORTING_NON_BLOCKING | Immediate previous completed-volume relationship is retained without threshold and cannot admit or veto |
| Path-clearance consequence | DEFERRED_METHODOLOGY | Threshold remains deferred |
| Extension consequence | DEFERRED_METHODOLOGY | Threshold remains deferred |
| Directional admission | V0_COMMISSIONED | Exact completed 1H + 15M + coherence Long/Short only; non-directional/conflict not admitted and unavailable remains unavailable |
| Candidate scoring/ranking | PROHIBITED_IN_V0 | No score, quota, ranking or top-N is commissioned |
| Additional failed-break/pivot sequencing | DEFERRED_METHODOLOGY | Validate factual need first |
| Historical completed 1D/1H/15M/5M reconstruction | REAL_EVIDENCE_RETAINED | WO-06S retained 47,945 completed candles with explicit completed-session EOD boundaries and no look-ahead; production Discovery identity is not reused |
| Historical previous-session H/L/C, CPR and Narrow CPR | REAL_EVIDENCE_RETAINED | DOMAIN-008 previous trading session and unchanged `NARROW_CPR_KGS_V0`; Part 3 consumes the retained fact without recalculation |
| Historical canonical/Provider subject binding | FAIL_CLOSED_EXACT_IDENTITY | No fuzzy match or current-symbol substitution; unresolved subjects remain unavailable |
| Historical MCX derivative contract | HISTORICAL_PREREQUISITE_UNAVAILABLE | Exact contract identity required; no active/front/nearest/liquidity/OI selection |

No `MISSING_REQUIRED_FOR_DISCOVERY` fact was found for the approved
non-threshold V0 contract. WO-04 is therefore skippable. This does not convert
deferred methodology into authority.

WO-06 Part 2 found no machine-fact enhancement required to implement the
research framework. Real evidence may still establish a precise later gap.

WO-06 Part 3 commissions only the approved Variant-G consequences recorded
above. Informational 1D/5M/PDH/PDL/CPR/Pivot facts retain no admission authority;
barrier/path, extension, ATR and SMA consequences remain deferred.

WO-06HA closed the engineering seam with a completed-session EOD boundary,
pre-acquisition request ceiling and explicit invocation. WO-06S later performed
the separately governed one-shot acquisition and retained the real evidence.
