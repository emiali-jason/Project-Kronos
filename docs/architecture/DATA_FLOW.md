# Project KRONOS Data Flow

**Status:** Canonical
**Date:** 2026-07-10

This document describes how information moves through KRONOS. It complements the [Architecture Overview](OVERVIEW.md) and [Engine Ownership Matrix](ENGINE_OWNERSHIP.md).

## End-to-End Flow

```text
MCX execution symbol + reference-market identity
  -> standardized primary/reference datasets
  -> market intelligence
  -> decision and readiness
  -> execution-context translation
  -> execution timing
  -> objective model-trade management
  -> confirmed execution alerts
  -> trader-facing display
```

Reference markets provide evidence. The MCX 1H chart owns the executable context.

## 1. Market Intelligence

```text
KR-200 Market Identification
  -> KR-250 Asset and Reference Mapping
  -> KR-260 Primary/Reference OHLCV
  -> KR-270 Indicators + KR-271 Math
  -> KR-275 Structure + KR-280 CPR
  -> KR-300 Trend
  -> KR-310 Quality
  -> KR-315 Compression
  -> KR-320 Acceptance
  -> KR-330 Momentum
  -> KR-340 Review Readiness
  -> KR-350 Opportunity
  -> KR-360 Confidence
```

Each intelligence engine answers one question and exposes public outputs. No individual indicator creates a trade.

## 2. Decision

KR-370 consumes prior public intelligence outputs and produces one progressive decision state:

- AVOID;
- WAIT;
- WATCH LONG;
- WATCH SHORT;
- BUY READY;
- SELL READY.

KR-370 owns direction and readiness. It does not issue BUY NOW or SELL NOW and does not access raw Daily/4H/1H market data.

```text
Intelligence public outputs
  -> KR-370 direction/readiness
  -> decision reason, blocker, review point, and checklist
```

## 3. Execution Context

KR-380A is a narrow adapter. It translates the minimum reference and execution facts needed by KR-380:

- Reference Daily directional permission;
- Reference 4H acceptance/compression readiness;
- Reference 1H momentum support;
- MCX 1H chart/context readiness;
- precise internal blockers for later trader-readable translation.

```text
KR-260/270 narrow reference datasets
  + prior public direction/readiness context
  -> KR-380A public adapter contract
  -> KR-380
```

KR-380A does not create separate Daily, 4H, and 1H copies of the intelligence core. The exception is governed by [ADL-003](ADL-003-Execution-Context-Adapters.md).

## 4. Execution Timing

KR-380 acts only when KR-370 says BUY READY or SELL READY.

```text
BUY READY  -> FORMING / EXTENDED / FAILED / BUY NOW
SELL READY -> FORMING / EXTENDED / FAILED / SELL NOW
Other KR-370 states -> NO TRIGGER
```

Final BUY NOW, SELL NOW, EXTENDED, and FAILED outcomes require confirmed MCX 1H context. KR-380 cannot infer a direction, reverse KR-370, or upgrade WATCH to an entry.

KR-380 also publishes an ordered blocker queue. KR-705 translates that queue into trader-readable Need, Next, and Then rows.

## 5. Model Trade Management

KR-390A supplies the narrow confirmed structure reference required for the initial and managed model stop. It uses completed MCX 1H execution bars and does not duplicate KR-275.

KR-390 starts a model trade only from confirmed `outTriggerBuy` or `outTriggerSell`.

```text
NO TRADE
  -> confirmed BUY NOW / SELL NOW
  -> HOLD
  -> PROTECT at qualifying progress
  -> TRAIL from confirmed structure
  -> EXIT on confirmed managed-stop breach

Invalid entry/stop data
  -> INVALIDATED
```

The model trade persists after KR-380 returns to NO TRIGGER. New triggers are ignored while a model trade is active. Managed risk must never loosen.

KR-390 tracks the objective KRONOS model trade whether or not the user personally entered. See [ADL-004](ADL-004-Model-Trade-Ownership.md).

## 6. Alerts

KR-400 consumes KR-380 public outputs only and defines two alert types:

- KRONOS BUY NOW;
- KRONOS SELL NOW.

The alert event fires only on the transition into the confirmed trigger state. A persistent trigger state must not produce duplicate alerts on later calculations.

```text
new confirmed outTriggerBuy edge  -> KRONOS BUY NOW alert
new confirmed outTriggerSell edge -> KRONOS SELL NOW alert
all other states                  -> no alert
```

TradingView handles alert creation, mobile push, and delivery. KRONOS places no broker order. See [ADL-005](ADL-005-Alert-Architecture.md).

## 7. Trader Display

KR-705 consumes public outputs and presents:

- trend, quality, acceptance, momentum, compression, opportunity, and confidence;
- KR-390 model-trade status in the Risk row;
- KR-380 execution state in the Entry row;
- KR-370 decision state in the Decision row;
- the most relevant decision or execution blockers in Need, Next, and Then;
- core data status.

KR-705 translates and displays. It does not calculate trading intelligence.

## Reference Charts Versus Execution Chart

| Context | Role | May issue executable MCX BUY NOW/SELL NOW? |
|---|---|---:|
| COMEX/NYMEX Daily | Strategic/reference support | No |
| COMEX/NYMEX 4H | Structure, acceptance, compression support | No |
| COMEX/NYMEX 1H | Momentum/timing support | No |
| MCX 1H | Self-contained execution venue | Yes, after KR-370 readiness and confirmed KR-380 timing |

Reference charts may expose their own analytical states for diagnostics, but they cannot issue an MCX executable trigger.

## Self-Contained MCX Execution Rule

On MCX 1H, every remaining blocker must be available in the same panel in trader language. The trader should not need to open COMEX merely to discover why execution is pending.

The source of a blocker may be reference Daily, reference 4H, reference 1H, or MCX 1H. Its presentation must describe the required market behavior, not leak internal engine naming. This decision is recorded in [ADL-002](ADL-002-MCX-Self-Contained-Execution.md).
