# KR-370 K5 Fact-Foundation Reconstructability Audit V1

Authority: RESEARCH ONLY / NON-AUTHORITATIVE

Source corpus:
`INTRADAY-QUALIFICATION-CORPUS-f70fadc6b256f3e6d5424598228c73e352684e2e789ba328de56c69f0cf5029f`
version `0.2.0`.

No Provider call, runtime operation, production mutation, or threshold selection
was performed.

## Result

| Fact | Available |
|---|---:|
| Observations considered | 465 |
| Deterministic governed structural origin | 0 |
| Completed-15M Wilder/RMA ATR-14 | 465 |
| 4-bar forward structural outcome | 0 |
| 8-bar forward structural outcome | 0 |
| 12-bar forward structural outcome | 0 |
| Fully qualified, each horizon | 0 |

Family composition is 455 Equity, 10 Index, and 0 MCX. Retained 15-minute
structure directions are 51 LONG, 165 SHORT, and 249 NON_DIRECTIONAL. No
observation retains an authoritative setup-family binding for either approved
setup family.

ATR reconstruction succeeds because every observation retains at least 14
completed governed 15-minute candles at its boundary. Origin reconstruction
remains unavailable because no observation binds its setup family to an
explicit governed directional move or explicit governed range/break structure.
Forward reconstruction remains unavailable because these observations occur at
the end-of-session boundary and retain no same-session future terminal
structure at 4, 8, or 12 completed 15-minute bars.

Therefore `K5_CORPUS_RECONSTRUCTION_READY = NO`. The factual contracts are
implemented, but the retained corpus is insufficient for empirical material-
extension threshold selection. The threshold remains `POLICY_UNRESOLVED`.
