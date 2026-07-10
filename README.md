# Project KRONOS

KRONOS Futures is a modular futures intelligence and decision-support platform built in Pine Script for TradingView.

It:

- analyzes execution and reference markets;
- produces explainable market decisions;
- confirms execution timing;
- manages objective model trades;
- sends confirmed BUY NOW / SELL NOW alerts.

It does not:

- place broker orders;
- guarantee profits;
- track the user's actual personal position yet;
- operate as an opaque black-box strategy.

## Current Supported Scope

**Supported Futures Model:** MCX Metals

| Execution instrument | Reference market |
|---|---|
| MCX Gold | `COMEX:GC1!` |
| MCX Silver | `COMEX:SI1!` |
| MCX Copper | `COMEX:HG1!` |

**Execution timeframe:** MCX 1H.

Reference markets support the execution decision. The MCX 1H chart is the self-contained execution context for confirmed BUY NOW and SELL NOW states.

## Planned Scope

- MCX Energy: Crude Oil and Natural Gas.
- NSE Stock Futures.

KRONOS follows the principle: **One Engine. Multiple Market Models.** Market-specific behavior should be handled through dependency profiles, reference symbols, weights, and thresholds rather than separate codebases.

## Architecture Summary

The current trader-facing flow is:

```text
KR-370 Decision
  -> KR-380A Execution Context Adapter
  -> KR-380 Execution Timing
  -> KR-390A Trade Management Adapter
  -> KR-390 Model Trade Management
  -> KR-400 Alerts
  -> KR-705 Trader Intelligence Panel
```

Ownership is strict:

- KR-370 owns direction and readiness.
- KR-380 owns execution timing.
- KR-390 owns the objective KRONOS model trade.
- KR-400 owns confirmed BUY NOW / SELL NOW alert events.
- KR-705 displays and translates intelligence for the trader.

## Current Status

- Intelligence, decision, and execution core through KR-380: Frozen.
- KR-390 Trade Management: Foundation.
- KR-400 Execution Alerts: Foundation.
- KR-705 Trader Intelligence Panel: Frozen display layer.
- Top-level product metadata remains `0.5.0 / 0004 / FOUNDATION` pending formal release-version reconciliation.

BUY NOW and SELL NOW are confirmed execution-timing states. They are not broker orders, and no automated trade is placed.

## Documentation

- [Architecture Overview](docs/architecture/OVERVIEW.md)
- [Engine Status](docs/ENGINE_STATUS.md)
- [Roadmap](ROADMAP.md)
- [Testing Protocol](docs/validation/TESTING.md)
- [MCX Metals Validation](docs/validation/MCX-METALS-VALIDATION.md)
- [Engineering Manual](docs/KRONOS_ENGINEERING_MANUAL.md)
- [Design Decisions](docs/Decisions.md)
- [Futures Model Architecture](docs/architecture/ADL-001-Futures-Model.md)
- [MCX Self-Contained Execution](docs/architecture/ADL-002-MCX-Self-Contained-Execution.md)
- [Execution Context Adapters](docs/architecture/ADL-003-Execution-Context-Adapters.md)
- [Model Trade Ownership](docs/architecture/ADL-004-Model-Trade-Ownership.md)
- [Alert Architecture](docs/architecture/ADL-005-Alert-Architecture.md)

## Technology

- Pine Script v6
- TradingView
- Git and GitHub

Designed and developed by Imran Ali. Software architecture developed collaboratively with ChatGPT/Codex.
