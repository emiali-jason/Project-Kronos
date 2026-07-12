# KRONOS Project Memory

**Status:** Permanent project briefing
**Date:** 2026-07-11

Read this document before starting any future KRONOS development chat. It is the compact briefing for where the project stands and what should happen next.

## 1. Current Platform Status

KRONOS is a modular market-intelligence and decision-support platform built in Pine Script for TradingView. It analyzes execution and reference markets, produces explainable decisions, confirms execution timing, manages objective model trades, and creates confirmed BUY NOW / SELL NOW TradingView alert events.

It is not broker automation, not a black-box AI, and not a personal-position tracker yet.

Current platform state:

- Core architecture is established.
- MCX Metals Swing is the current completed market model.
- Intelligence, decision, and execution core through KR-380 is treated as frozen by the current product roadmap.
- KR-390 and KR-400 remain Foundation until live validation matures.
- KR-705 is the frozen trader-facing display layer.

## 2. Major Architectural Discovery

During NSE implementation, KRONOS evolved from a Futures-only platform into a unified Intelligence Platform.

The engine now separates:

```text
Analysis
  -> Intelligence
  -> Execution
```

Execution modules can vary while the intelligence engine remains unchanged.

Current execution modules:

- Cash
- Futures

Future execution modules:

- Options

This discovery is considered one of the major architectural milestones of Project KRONOS.

## 3. Current Market Models

Current:

- MCX Metals.

Next:

- MCX Energy.

Then:

- NSE Stock Futures.

Current MCX Metals references:

| Execution asset | Reference symbol |
|---|---|
| Gold | `COMEX:GC1!` |
| Silver | `COMEX:SI1!` |
| Copper | `COMEX:HG1!` |

See [ADL-001](../architecture/ADL-001-Futures-Model.md) and [MCX Metals Validation](../validation/MCX-METALS-VALIDATION.md).

## 4. Current Execution Profile

Current execution profile:

- Swing.

Future execution profile:

- Intraday.

Intraday execution profiles are deferred until after Platform v1.0. They should not be mixed into current Swing logic without a formal architecture decision.

## 5. Current Engine Status

Brief status only:

- KR-280 through KR-380 form the current intelligence, decision, and execution-timing core.
- KR-380A is the narrow execution-context adapter.
- KR-390A is the narrow trade-management adapter.
- KR-390 manages the objective KRONOS model trade and remains Foundation.
- KR-400 owns confirmed BUY NOW / SELL NOW TradingView alert events and remains Foundation.
- KR-705 displays and translates trader-facing intelligence.

Do not duplicate the full engine registry here. Read [Engine Status](../ENGINE_STATUS.md) and [Engine Ownership](../architecture/ENGINE_OWNERSHIP.md) before changing code.

## 6. Current Documentation Status

Architecture:

- Canonical overview, ownership, data flow, and ADLs exist.

Engineering:

- Engineering manual and Codex instructions define operating rules.

Validation:

- Testing protocol and MCX Metals validation record exist.
- Live-event validation is incomplete and must not be overstated.

Product:

- [KRONOS Vision & Roadmap](KRONOS_VISION_AND_ROADMAP.md) is the CEO-level product document.
- This file is the permanent project briefing for future sessions.

## 7. Current Priorities

1. MCX Energy
2. NSE Swing
3. Documentation Phase 3
4. KRONOS Platform v1.0
5. Intraday Execution Profiles
6. Personal Trading Layer
7. Analytics
8. AI

## 8. Deferred Decisions

Deferred decisions are summarized in [KRONOS Vision & Roadmap](KRONOS_VISION_AND_ROADMAP.md):

- DD-001: Reconcile the preserved legacy Auto CPR mode name after NSE Swing; KES (KRONOS Evidence Synthesis) remains the evidence synthesis boundary.
- DD-002: Execution Profiles from Swing to Intraday after Platform v1.0.
- DD-003: VWAP Evaluation deferred.
- DD-004: Macro Event Engine deferred.

These should become formal ADLs before implementation.

## 9. Important Engineering Principles

- One Engine One Responsibility: each engine owns one question.
- Public Outputs: downstream engines should consume public `out...` contracts.
- Frozen Contracts: frozen modules change only through scoped fixes, additive compatibility, or versioned changes.
- Adapter Pattern: adapters are narrow bridges, not duplicated intelligence stacks.
- Explainable Intelligence: decisions, timing, blockers, model trade state, and alerts must remain inspectable.
- MCX Self-contained Execution: the MCX 1H panel must explain execution blockers without requiring reference-chart inspection.

## 10. How to Start a New KRONOS Development Session

For every future KRONOS development chat:

1. Read `docs/product/KRONOS_PROJECT_MEMORY.md`.
2. Read [Engine Status](../ENGINE_STATUS.md).
3. Read [Engine Ownership](../architecture/ENGINE_OWNERSHIP.md).
4. Read the relevant ADLs:
   - [ADL-001 Futures Model](../architecture/ADL-001-Futures-Model.md)
   - [ADL-002 MCX Self-Contained Execution](../architecture/ADL-002-MCX-Self-Contained-Execution.md)
   - [ADL-003 Execution Context Adapters](../architecture/ADL-003-Execution-Context-Adapters.md)
   - [ADL-004 Model Trade Ownership](../architecture/ADL-004-Model-Trade-Ownership.md)
   - [ADL-005 Alert Architecture](../architecture/ADL-005-Alert-Architecture.md)
5. Continue from the documented roadmap instead of relying on old chat history.

## Canonical References

- [KRONOS Vision & Roadmap](KRONOS_VISION_AND_ROADMAP.md)
- [Architecture Overview](../architecture/OVERVIEW.md)
- [Data Flow](../architecture/DATA_FLOW.md)
- [Testing Protocol](../validation/TESTING.md)
- [Roadmap](../../ROADMAP.md)
