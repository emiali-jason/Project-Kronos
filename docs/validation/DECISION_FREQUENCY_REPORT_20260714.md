# KRONOS Decision Frequency Report - 20260714

## Summary

- Date: 2026-07-14
- Total charts reviewed: 6
- WAIT: 0
- WATCH LONG: 0
- WATCH SHORT: 0
- BUY READY: 4
- SELL READY: 2
- READY total: 6
- WATCH total: 0
- BUY NOW: 0
- SELL NOW: 0
- Execution NOW total: 0
- Unique instruments: 6
- Repository rows in source log: 6
- Trading logic changed: No

## Decision Distribution

| Value | Count |
|---|---:|
| WAIT | 0 |
| WATCH LONG | 0 |
| WATCH SHORT | 0 |
| BUY READY | 4 |
| SELL READY | 2 |

## Execution-State Distribution

| Value | Count |
|---|---:|
| NO TRIGGER | 0 |
| FORMING | 0 |
| BUY NOW | 0 |
| SELL NOW | 0 |
| EXTENDED | 0 |
| FAILED | 0 |
| Unspecified | 6 |

## Blocking Conditions Ranked

| Value | Count |
|---|---:|
| Unspecified | 6 |

## Markets

| Value | Count |
|---|---:|
| NSE | 6 |

## Timeframes

| Value | Count |
|---|---:|
| Unspecified | 6 |

## Trend States

| Value | Count |
|---|---:|
| Unspecified | 6 |

## Acceptance States

| Value | Count |
|---|---:|
| Unspecified | 6 |

## Momentum States

| Value | Count |
|---|---:|
| Unspecified | 6 |

## Unresolved Validation Questions

- Does execution-state scarcity reflect expected strictness or an execution-timing bottleneck?
- Which blocker dominates after the full reviewed chart set is entered with chart-level rows?
- Are READY states failing to advance because KR-380 execution timing is rare, or because execution-state fields were not captured in the reviewed screenshots?
- No trading logic, thresholds, confidence calculations, architecture, or execution rules were changed by this validation report.

## Chart-Level Records

| Validation ID | Instrument | Market | Timeframe | Decision | First Unmet Requirement | Confidence | Trend | Acceptance | Momentum | Execution |
|---|---|---|---|---|---|---:|---|---|---|---|
| KR-DFV-20260714-001 | Divis Laboratories | NSE | - | BUY READY | - | - | - | - | - | - |
| KR-DFV-20260714-002 | Adani Green Energy | NSE | - | BUY READY | - | - | - | - | - | - |
| KR-DFV-20260714-003 | Apollo Hospitals | NSE | - | BUY READY | - | - | - | - | - | - |
| KR-DFV-20260714-004 | Lupin | NSE | - | BUY READY | - | - | - | - | - | - |
| KR-DFV-20260714-005 | HDFC Life | NSE | - | SELL READY | - | - | - | - | - | - |
| KR-DFV-20260714-006 | IOC | NSE | - | SELL READY | - | - | - | - | - | - |

## Method

- CSV source of truth: `data/validation/decision_frequency/KRONOS_DECISION_FREQUENCY_LOG.csv`
- Current Decision maps to KR-370 / KR-705 Decision.
- First unmet requirement maps to KR-370 primary blocker or the first unchecked KR-705 Need item.
- Confidence maps to KR-360 score.
- Trend, Acceptance, and Momentum map to KR-300, KR-320, and KR-330 displayed states.
- Execution maps to KR-380 displayed state when visible.
- This report makes no trading decision and changes no thresholds.

## Known Limitations

- TradingView chart values must be entered into the CSV before aggregate statistics can represent the reviewed chart universe.
- The analyzer ranks recorded blockers; it does not infer missing chart states from screenshots.
- Empty reports are expected until approved validation rows are recorded.
