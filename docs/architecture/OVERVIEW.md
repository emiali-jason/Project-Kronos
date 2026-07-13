# Project KRONOS Architecture Overview

**Status:** Canonical
**Date:** 2026-07-10

## Product Definition

KRONOS Futures is a modular futures intelligence and decision-support platform.

It:

- analyzes reference and execution markets;
- produces explainable directional and readiness decisions;
- confirms execution timing on the execution chart;
- manages an objective KRONOS model trade after a confirmed trigger;
- sends TradingView alerts for confirmed execution events;
- presents the result through a trader-facing intelligence panel.

It is not:

- broker automation;
- a guaranteed-profit system;
- an opaque black-box strategy;
- a personal-position tracker yet.

BUY NOW and SELL NOW are explicit, confirmed execution-timing states. They are not broker orders and do not mean that an automated trade has been placed.

## Architecture Layers

| Layer | Responsibility | Primary engines |
|---|---|---|
| Configuration and identity | Product settings, market recognition, asset/reference mapping | KR-100, KR-200, KR-250 |
| Market data and mathematical foundation | Multi-timeframe OHLCV, indicators, math, and structure | KR-260, KR-270, KR-271, KR-275, KR-280 |
| Intelligence Core | Trend, quality, compression, acceptance, momentum, review, consolidated directional bias, opportunity, evidence synthesis, confidence | KR-300 through KR-360 plus KES (KRONOS Evidence Synthesis) |
| Decision | Direction and readiness | KR-370 |
| Execution context | Narrow translation of reference and MCX execution facts | KR-380A |
| Execution timing | Confirmed NO TRIGGER/FORMING/BUY NOW/SELL NOW/EXTENDED/FAILED state | KR-380 |
| Model trade management | Persistent objective model entry, protection, trailing, and exit state | KR-390A, KR-390 |
| Alerts | Event-edge TradingView notifications | KR-400 |
| Trader interface | Display and trader-readable translation | KR-705 |

Detailed boundaries are defined in [Engine Ownership](ENGINE_OWNERSHIP.md).

KR-341 provides the swing-trading directional contract inside the Intelligence Core. Weekly Neutral is permissive, Confirmed Daily direction is mandatory for READY permission, Developing Daily supports WATCH only, and Neutral and Conflicted are distinct consolidation states.

## Current Conceptual Data Flow

```text
Reference and execution market identity
  -> KR-250 Asset Mapping
  -> KR-260 Market Data
  -> KR-270 / KR-271 / KR-275 / KR-280 Foundation
  -> KR-300 through KR-350 Evidence Generation
  -> KR-341 Consolidated Directional Bias
  -> KES Evidence Synthesis
  -> KR-360 Confidence
  -> KR-370 Decision and Readiness
  -> KR-380A Execution Context Adapter
  -> KR-380 Execution Timing
  -> KR-390A Trade Management Adapter
  -> KR-390 Objective Model Trade
  -> KR-400 Confirmed Execution Alerts
  -> KR-705 Trader Intelligence Panel
```

The exact source-file declaration order may differ from this conceptual diagram. Ownership remains one-way: later engines consume established public contracts, and adapters may bridge only the narrow facts authorized by [ADL-003](ADL-003-Execution-Context-Adapters.md).

See [Data Flow](DATA_FLOW.md) for the detailed paths.

## Evidence Synthesis Boundary

KES collects, validates, standardizes, and packages evidence before KR-360 Confidence.

KES does not own evidence generation, confidence calculation, decisions, execution, trade management, alerts, or presentation. It is an unnumbered architectural boundary over existing public evidence contracts; it does not add or renumber an engine.

## Current Supported Futures Model

### MCX Metals

| Execution instrument | Reference market |
|---|---|
| MCX Gold | `COMEX:GC1!` |
| MCX Silver | `COMEX:SI1!` |
| MCX Copper | `COMEX:HG1!` |

Supporting reference context:

- Reference Daily;
- Reference 4H;
- Reference 1H.

Execution context:

- MCX 1H only for confirmed BUY NOW and SELL NOW events.

COMEX charts support the decision. They are not MCX execution venues and cannot issue executable MCX triggers.

Validation scope is recorded in [MCX Metals Validation](../validation/MCX-METALS-VALIDATION.md).

## Planned Model Expansion

- MCX Energy: Crude Oil and Natural Gas.
- NSE Stock Futures.
- Futures Model selector: Auto plus manual override.

Reference mappings or recognition scaffolding in source do not by themselves make a planned model supported.

## Core Architecture Principles

1. **One engine, one responsibility.** Each engine answers one primary question.
2. **Public contracts.** Downstream engines consume stable public outputs wherever possible.
3. **Narrow adapter exceptions.** An adapter may bridge a missing low-level fact, but may not recreate a full intelligence stack.
4. **Confirmed-bar finality.** Actionable execution, trade start, stop breach, and alert events require confirmed execution context.
5. **Frozen-contract discipline.** Frozen behavior changes only through additive compatibility, scoped bug fixes, or a declared version change.
6. **MCX execution-chart self-containment.** The MCX 1H chart must explain every blocker without requiring the trader to inspect a reference chart.
7. **One Engine. Multiple Market Models.** Market-specific symbols, weights, and thresholds adapt the common engine architecture.

## Ownership Summary

```text
KR-370 decides direction and readiness.
KR-380 decides entry timing.
KR-390 manages the objective model trade.
KR-400 emits confirmed execution alerts.
KR-705 displays and translates intelligence for the trader.
```

These boundaries are contracts, not informal naming conventions.
