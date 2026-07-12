# KRONOS Pine and TradingView Validation Protocol

**Status:** Canonical
**Date:** 2026-07-10

This protocol replaces generic software-test guidance for the Pine implementation. KRONOS validation combines repository checks, source review, TradingView compilation, visual inspection, and replay/live event evidence.

## Evidence Rule

Never collapse these into one word:

- **Static:** source and dependency path inspected.
- **Compile:** exact revision compiled in TradingView.
- **Visual:** behavior observed on a named symbol/timeframe.
- **Replay/live event:** state transition occurred and was observed on confirmed bars.

A static check cannot prove runtime behavior. A compile cannot prove state correctness. A screenshot cannot prove event-edge behavior.

## Pre-Compile Repository Checks

1. Run `git diff --check`.
2. Confirm the diff contains only intended files and engine boundaries.
3. Search for compiler-risk patterns in history-dependent functions such as `ta.rma`, `ta.ema`, `ta.sma`, `ta.highest`, and `ta.lowest` inside conditional scopes.
4. Review every added or changed `request.security()` call.
5. Confirm no request path can receive `""` or `"UNKNOWN"`.
6. Confirm public-output names and state constants remain compatible.
7. Confirm table dimensions match the highest row/column used and `table.clear()` bounds.

## TradingView Compile Review

For the exact commit under test:

- paste/load the complete Pine source in TradingView;
- compile with Pine Script v6;
- record compiler errors and warnings exactly;
- resolve or explicitly accept every history-consistency warning;
- reload the script after compilation;
- record any runtime error before testing logic;
- capture the script version/build shown by source metadata, even when it is known to require reconciliation.

Passing `git diff --check` is not a Pine compile result.

## Supported-Symbol Matrix

| Model | Execution chart | Reference symbol | Support state | Required result |
|---|---|---|---|---|
| MCX Metals | Active MCX Gold contract | `COMEX:GC1!` and representative dated GC contract | Current | No runtime error; correct mapping; reference context available; execution restricted to MCX 1H |
| MCX Metals | Active MCX Silver contract | `COMEX:SI1!` and representative dated SI contract | Current | Same checks as Gold |
| MCX Metals | Active MCX Copper contract | `COMEX:HG1!` and representative dated HG contract | Current | Same checks as Gold |
| MCX Energy | Active MCX Crude contract | `NYMEX:CL1!` | Planned | Mapping/safety smoke test only; do not claim model support |
| MCX Energy | Active MCX Natural Gas contract | `NYMEX:NG1!` | Planned | Mapping/safety smoke test only; do not claim model support |
| NSE Stock Futures | Representative index and stock futures | Underlying/index references to be specified | Planned | No release claim until model profile and references are approved |

Test both continuous reference symbols and representative dated reference contracts where TradingView provides them.

## Timeframe Matrix

| Chart timeframe | Expected role | Executable MCX BUY NOW/SELL NOW? | Required checks |
|---|---|---:|---|
| 15 minutes | Lower-timeframe diagnostics/reference behavior | No | CPR route, no accidental trigger, panel remains coherent |
| 60 minutes | MCX execution context | Yes, only after all gates and confirmed bar | Self-contained blockers, trigger finality, alert edge, model-trade start |
| 240 minutes | Structure/reference support | No | Reference 4H readiness and no executable trigger |
| Daily | Trend/reference support | No | Stable trend/reference behavior and no executable trigger |
| Weekly | Strategic/reference support | No | Data availability and no executable trigger |

For legacy Auto CPR routing, explicitly check the selected reference timeframe on 15m, 1H, 4H, Daily, and Weekly charts against the approved KR-280 contract.

## Reference-Symbol and Runtime Safety

For every symbol in the matrix:

- verify root/ticker/description recognition;
- verify the resolved reference symbol;
- verify COMEX/NYMEX reference charts use a safe current-symbol request path;
- verify unsupported symbols expose unavailable data safely;
- verify no `request.security()` call receives `UNKNOWN` or an empty symbol;
- inspect the TradingView runtime log after chart load and symbol/timeframe changes;
- test session boundaries and contract rollover where practical.

## Repaint and Lookahead Review

Review each higher-timeframe or history-dependent input for:

- `lookahead` setting;
- `gaps` setting;
- whether indexing occurs inside or outside `request.security()`;
- whether the value represents a completed or developing candle;
- whether a swing or range excludes the current execution bar where required;
- whether persistent memory changes only from permitted confirmed events.

Actionable execution must never depend on future-looking data.

## State Exclusivity

On every tested bar, verify:

- one KR-370 decision state is active;
- one KR-380 trigger state is active;
- one KR-390 management state is active;
- BUY and SELL cannot both be true;
- BUY NOW cannot originate from WATCH LONG;
- SELL NOW cannot originate from WATCH SHORT;
- a reference chart cannot enter an MCX executable state.

## Confirmed-Bar Trigger Review

On MCX 1H replay/live bars:

1. Observe FORMING while the bar or requirements are incomplete.
2. Confirm BUY NOW/SELL NOW appears only after KR-370 READY direction and all KR-380 gates.
3. Confirm final trigger events require `barstate.isconfirmed` and MCX 1H context.
4. Reload the chart and verify historical final states do not move unexpectedly.
5. Confirm COMEX/NYMEX charts remain non-executable.

## Persistent Model-Trade Review

For KR-390:

- verify no trade starts from WATCH, READY, FORMING, or NO TRIGGER;
- verify the model entry uses the confirmed MCX 1H trigger-bar close;
- verify the initial stop comes from the KR-390A completed-bar structure reference;
- verify the model remains active after KR-380 returns to NO TRIGGER;
- verify a new trigger is ignored while active;
- verify long managed stops never fall and short managed stops never rise;
- verify PROTECT occurs only at the documented progress threshold;
- verify TRAIL uses confirmed structure and does not loosen risk;
- verify EXIT requires a confirmed MCX 1H close through the managed stop;
- verify unavailable/invalid entry or stop data produces INVALIDATED rather than an active trade.

## Alert Edge and Duplicate Review

KR-400 currently has exactly two alerts.

For BUY and SELL separately:

1. Create the TradingView alert from the corresponding condition.
2. Trigger the state in replay/live validation.
3. Confirm one alert on the transition into BUY NOW or SELL NOW.
4. Confirm no duplicate while the same trigger state persists.
5. Confirm no alert from FORMING, EXTENDED, FAILED, WATCH, READY, HOLD, PROTECT, TRAIL, or EXIT.
6. Confirm no alert on COMEX/NYMEX reference charts.
7. Record TradingView log delivery separately from mobile push delivery.

Mobile push requires TradingView notifications and is not broker automation.

## KR-705 Visual Review

Capture desktop screenshots for every supported metal on MCX 1H and at least one supporting reference chart.

Verify:

- no text overlap or truncation that changes meaning;
- Decision displays KR-370;
- Entry displays KR-380;
- Risk displays KR-390 model-trade state;
- Need/Next/Then preserve priority and suppress duplicates;
- empty checklist values display the intended placeholder;
- table row count and `table.clear()` bounds match;
- self-contained blockers use trader-readable wording.

## Reusable Validation Matrix

| Date | Commit | Model | Execution symbol | Reference symbol | Timeframe | Static | Compile | Runtime | Visual | Replay/live event | Result | Evidence link / notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| YYYY-MM-DD | hash | MCX Metals | MCX Gold contract | COMEX:GC1! | 60 | Pass/Fail | Pass/Fail | Pass/Fail | Pass/Fail | State observed | Pass/Fail | Screenshot/log |
| YYYY-MM-DD | hash | MCX Metals | MCX Silver contract | COMEX:SI1! | 60 | Pass/Fail | Pass/Fail | Pass/Fail | Pass/Fail | State observed | Pass/Fail | Screenshot/log |
| YYYY-MM-DD | hash | MCX Metals | MCX Copper contract | COMEX:HG1! | 60 | Pass/Fail | Pass/Fail | Pass/Fail | Pass/Fail | State observed | Pass/Fail | Screenshot/log |
| YYYY-MM-DD | hash | MCX Energy | MCX Crude contract | NYMEX:CL1! | 60 | Smoke | Pass/Fail | Pass/Fail | Not supported | Not supported | Informational | Notes |
| YYYY-MM-DD | hash | MCX Energy | MCX Natural Gas contract | NYMEX:NG1! | 60 | Smoke | Pass/Fail | Pass/Fail | Not supported | Not supported | Informational | Notes |
| YYYY-MM-DD | hash | NSE Stock Futures | Contract | TBD | TBD | Planned | Planned | Planned | Planned | Planned | Not tested | Notes |

## Validation Completion Rule

A feature may be called:

- **statically verified** after source review;
- **compile clean** only after the exact revision compiles with warnings reviewed;
- **visually validated** only with a named symbol/timeframe observation;
- **live-event validated** only after the exact transition and persistence behavior is observed.

Record partial evidence honestly. Do not promote planned models or unobserved states to validated status.
