# Project KRONOS Engineering Manual

**Status:** Normative engineering reference
**Date:** 2026-07-10

This manual defines the stable engineering rules for KRONOS. Current per-engine metadata belongs in [Engine Status](ENGINE_STATUS.md), not in duplicated tables inside this manual.

## 1. Product Vision

KRONOS Futures is a modular futures intelligence and decision-support platform for TradingView. Its purpose is to help a trader understand market direction, readiness, execution timing, and objective model-trade state through a transparent engine architecture.

KRONOS should warn early, but signal only after confirmation.

## 2. What KRONOS Is

KRONOS is a structured market-intelligence system. It:

- analyzes execution and reference markets;
- builds evidence through independent engines;
- produces explainable decisions;
- confirms execution timing;
- manages an objective KRONOS model trade;
- emits TradingView alerts for confirmed BUY NOW and SELL NOW events;
- displays trader-facing intelligence through KR-705.

Current supported scope is MCX Metals: Gold, Silver, and Copper.

## 3. What KRONOS Is Not

KRONOS is not:

- broker automation;
- a guaranteed-profit system;
- a personal-position tracker yet;
- an opaque black-box strategy;
- an options framework in the current phase;
- a portfolio automation system.

BUY NOW and SELL NOW are confirmed execution-timing states. They are not broker orders.

## 4. Design Principles

- One engine, one responsibility.
- Public outputs are the normal dependency contract.
- Frozen contracts are respected.
- Adapters are narrow exceptions, not permission to duplicate the intelligence core.
- Confirmed-bar finality is required for actionable states.
- One Engine. Multiple Market Models.
- Documentation must state what is verified, what is planned, and what is unknown.

## 5. Layered Architecture

KRONOS is layered from market identity to trader display:

```text
Configuration and identity
  -> market data and mathematical foundation
  -> intelligence core
  -> decision
  -> execution context
  -> execution timing
  -> model trade management
  -> alerts
  -> trader-facing display
```

The canonical architecture is documented in [Architecture Overview](architecture/OVERVIEW.md) and [Data Flow](architecture/DATA_FLOW.md).

## 6. Engine Ownership

Engine ownership is exclusive. Downstream engines may consume public outputs but must not silently recreate or reverse upstream responsibilities.

Key ownership boundaries:

- KR-370 owns decision and readiness.
- KR-380 owns execution timing.
- KR-390 owns objective model-trade state and protection.
- KR-400 owns confirmed BUY NOW / SELL NOW alert events.
- KR-705 owns trader-facing display and translation.

The full matrix is maintained in [Engine Ownership](architecture/ENGINE_OWNERSHIP.md).

## 7. Public-Output Contracts

Mature engines expose public outputs for downstream consumers. Public outputs should be stable, explicit, and additive where possible.

Rules:

- Prefer `out...` outputs over internal variables.
- Do not consume another engine's private calculations when a public output exists.
- If a public output must change, preserve compatibility or document the breaking change.
- Do not expose unnecessary internals merely for convenience.

## 8. Adapter Pattern

Adapters are allowed only when a later engine needs a narrow lower-level fact that does not yet exist as a formal public output.

Current adapter examples:

- KR-380A: execution-context adapter for reference and MCX 1H timing facts.
- KR-390A: trade-management adapter for confirmed execution swing references.

Adapters must not duplicate Daily, 4H, and 1H copies of the entire intelligence core. See [ADL-003](architecture/ADL-003-Execution-Context-Adapters.md).

## 9. Frozen-Module Policy

Frozen modules can change only through:

- scoped bug fixes;
- additive compatibility-safe outputs;
- performance improvements that preserve behavior;
- a declared version change.

A frozen module must not receive casual behavior changes, hidden new responsibilities, or unrelated refactors. Current status is recorded in [Engine Status](ENGINE_STATUS.md).

## 10. Confirmed-Bar Finality

Actionable states must use confirmed-bar gates where applicable:

- KR-380 final BUY NOW, SELL NOW, EXTENDED, and FAILED states;
- KR-390 model trade starts and exits;
- KR-400 alert events.

Intrabar states may describe formation, but final execution outcomes must not repaint into false certainty.

## 11. Futures Model Architecture

KRONOS uses one engine architecture across multiple futures models.

Current supported model:

- MCX Metals: Gold, Silver, Copper.

Planned models:

- MCX Energy: Crude Oil, Natural Gas.
- NSE Stock Futures.

Market-specific behavior is controlled by dependency profiles, reference symbols, weights, thresholds, and eventually a Futures Model selector. See [ADL-001](architecture/ADL-001-Futures-Model.md).

## 12. MCX Self-Contained Execution Rule

The MCX 1H execution chart must explain the execution state and blockers without requiring the trader to inspect COMEX reference charts.

Reference markets support the decision. MCX 1H owns executable context for MCX triggers. See [ADL-002](architecture/ADL-002-MCX-Self-Contained-Execution.md).

## 13. Model Trade Versus Personal Trade

KR-390 manages the objective KRONOS model trade after a confirmed KR-380 trigger. It does not know whether the user personally entered, skipped, scaled, or exited.

Personal trade tracking is a future capability and must not be mixed into KR-390 without a formal ownership decision. See [ADL-004](architecture/ADL-004-Model-Trade-Ownership.md).

## 14. Alert Ownership

KR-400 owns exactly the alert event edge for confirmed BUY NOW and SELL NOW states. It consumes KR-380 public outputs and must not calculate trend, confidence, execution timing, stops, or trade management.

TradingView delivers alerts and mobile notifications. KRONOS does not place broker orders. See [ADL-005](architecture/ADL-005-Alert-Architecture.md).

## 15. KR-705 Trader-Facing Display Ownership

KR-705 is the trader-facing intelligence/display layer. It consumes public outputs and presents concise status, decision, entry, model trade, and blocker information.

KR-705 must not calculate trading intelligence, issue alerts, decide entries, or manage trades. It should not expose internal diagnostic variables unless temporarily debugging.

## 16. Development Workflow

Before changing code:

1. Read the relevant canonical docs.
2. Identify the engine owner and downstream consumers.
3. Confirm whether any frozen contract is affected.
4. Decide whether a narrow adapter is required.

During implementation:

1. Keep the scope narrow.
2. Preserve public outputs unless explicitly changing them.
3. Avoid unrelated refactors.
4. Keep comments and metadata truthful.

Before finishing:

1. Run `git diff --check`.
2. Confirm Pine logic changes are intentional.
3. Summarize changed files, risks, and validation requirements.

## 17. Validation Workflow

Validation has distinct evidence levels:

- static source review;
- TradingView compile evidence;
- visual validation;
- replay/live event validation.

Do not claim full live validation from static inspection alone. Use [Testing Protocol](validation/TESTING.md) and [MCX Metals Validation](validation/MCX-METALS-VALIDATION.md).

## 18. Documentation Hierarchy

Canonical documents:

- [Architecture Overview](architecture/OVERVIEW.md)
- [Engine Ownership](architecture/ENGINE_OWNERSHIP.md)
- [Data Flow](architecture/DATA_FLOW.md)
- [Engine Status](ENGINE_STATUS.md)
- [Testing Protocol](validation/TESTING.md)
- [MCX Metals Validation](validation/MCX-METALS-VALIDATION.md)
- [ADLs](architecture/ADL-001-Futures-Model.md)

Historical documents such as [Decisions](Decisions.md) should be preserved and amended only additively unless a task explicitly authorizes a rewrite.

## 19. Versioning Note

Top-level product metadata currently remains `0.5.0 / 0004 / FOUNDATION`. That metadata is pending formal release-version reconciliation.

Do not invent release versions, build numbers, or validation claims. Engine-level source headers and [Engine Status](ENGINE_STATUS.md) provide current implementation metadata.

## 20. Canonical Links

- [README](../README.md)
- [Roadmap](../ROADMAP.md)
- [Codex Instructions](../CODEX_INSTRUCTIONS.md)
- [Engine Specifications](EngineSpecifications.md)
- [Architecture Overview](architecture/OVERVIEW.md)
- [Engine Ownership](architecture/ENGINE_OWNERSHIP.md)
- [Data Flow](architecture/DATA_FLOW.md)
- [Engine Status](ENGINE_STATUS.md)
- [Testing Protocol](validation/TESTING.md)
- [MCX Metals Validation](validation/MCX-METALS-VALIDATION.md)
- [Futures Model ADL](architecture/ADL-001-Futures-Model.md)
- [MCX Self-Contained Execution ADL](architecture/ADL-002-MCX-Self-Contained-Execution.md)
- [Execution Context Adapter ADL](architecture/ADL-003-Execution-Context-Adapters.md)
- [Model Trade ADL](architecture/ADL-004-Model-Trade-Ownership.md)
- [Alert ADL](architecture/ADL-005-Alert-Architecture.md)
