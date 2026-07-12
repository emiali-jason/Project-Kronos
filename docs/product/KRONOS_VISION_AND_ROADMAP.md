# KRONOS Vision & Roadmap

**Version:** 1.1
**Status:** Living Document

## 1. Vision

KRONOS is a market-intelligence platform with multiple execution modules. It began as KRONOS Futures, but NSE implementation clarified a larger architecture: one intelligence engine can analyze markets, produce explainable BUY/SELL decisions, and route those decisions through different execution vehicles.

KRONOS is not:

- broker automation;
- a black-box AI;
- a signal-selling system.

KRONOS is:

- explainable;
- modular;
- reusable;
- extensible;
- execution-aware.

The platform should help a trader understand why the market is or is not ready, why execution is or is not allowed, and what objective model trade state KRONOS is tracking after a confirmed trigger. BUY NOW and SELL NOW are confirmed execution-timing states, not broker orders.

## 2. Mission

The long-term mission is to build a professional market-intelligence platform that can support disciplined trading decisions across market models and execution vehicles without fragmenting into separate scripts, private logic branches, or opaque signal rules.

KRONOS should preserve trader judgment while reducing confusion. It should organize market evidence, expose blockers, and separate analysis, intelligence, execution, model-trade management, and alerts into clear ownership layers.

## 3. Project North Star

"Build the most disciplined, explainable and reusable market-intelligence platform possible using one shared intelligence architecture across multiple market models and execution modules."

## 4. Core Design Philosophy

### One Engine, One Responsibility

Every engine answers one question. KR-370 decides direction and readiness. KR-380 decides timing. KR-390 manages the objective model trade. KR-400 owns alert events. KR-705 displays intelligence for the trader.

### Public Output Contracts

Downstream engines should consume stable public `out...` outputs instead of internal variables. This keeps ownership visible and prevents hidden coupling.

### Frozen Modules

Frozen modules should change only through scoped bug fixes, additive compatibility-safe outputs, performance improvements that preserve behavior, or a declared version change.

### Adapter Pattern

Adapters are narrow exceptions. They may translate minimum lower-level facts that do not yet exist as formal public outputs. They must not duplicate the full intelligence core for Daily, 4H, and 1H.

### Confirmed Bar Finality

Actionable execution states, model-trade starts, model-trade exits, and alert events must respect confirmed-bar finality where applicable.

### Model Trade before Personal Trade

KR-390 tracks the objective KRONOS model trade. It does not yet track the user's actual personal position. Personal trade management is a later product layer.

### Explainable Intelligence

KRONOS must show reasons, blockers, and status in trader language. A trader should understand the state without reverse-engineering internal engine names.

### One Intelligence Engine, Multiple Execution Modules

The same intelligence engine should support multiple execution paths. Market-specific behavior belongs in dependency profiles, reference symbols, weights, thresholds, and execution modules. The architecture should not split into separate codebases for cash, futures, options, metals, energy, equities, or indices.

## 5. Execution Philosophy

KRONOS separates three concerns:

1. Analysis
2. Intelligence
3. Execution

Analysis asks what market should be studied. Intelligence asks whether conditions justify a BUY or SELL decision. Execution asks which supported vehicle can express that decision.

One intelligence engine supports multiple execution paths.

Current execution modules:

- Cash
- Futures

Future execution modules:

- Options
- Others

### Examples

#### RELIANCE

Analysis:

- NSE Cash

Execution:

- Cash + Futures

#### 3M INDIA

Analysis:

- NSE Cash

Execution:

- Cash Only

#### NIFTY

Analysis:

- NSE Index

Execution:

- Futures

#### MCX GOLD

Analysis:

- MCX Futures

Execution:

- Futures

The BUY/SELL signal never changes. Only the execution vehicle changes.

## 6. Platform Architecture

```text
KRONOS Core Intelligence
  -> Execution Modules
       - Cash
       - Futures
       - Options (Future)
  -> KRONOS Discover (Future)
  -> KRONOS Analytics (Future)
```

### Market Models

Market Models define what market is being analyzed and what reference dependencies matter. Current and planned models include MCX Metals Swing, MCX Energy Swing, NSE Equity Swing, and NSE Index Swing.

### Execution Modules

Execution Modules define how a decision can be expressed. Current modules are Cash and Futures. Options are a future module, not active development.

### Shared Intelligence Engines

The shared engines analyze trend, quality, compression, acceptance, momentum, readiness, opportunity, confidence, decisions, execution timing, model trades, and alerts. They should remain generic and reusable.

### Trader Layer

The trader layer is the human-facing interpretation layer. KR-705 is the current panel. It displays public engine outputs and should not own trading decisions.

### Future Product Layers

Future products may consume KRONOS intelligence, but they must not implement independent trading logic.

## 7. Current Platform Status

### Completed / Foundation

- Core Intelligence architecture.
- Configuration Layer for current Swing market models.
- MCX Metals Swing validation record.

### In Progress

- MCX Energy Swing.
- NSE Equity Swing configuration and market-data integration planning.
- NSE Index Swing configuration and market-data integration planning.

### Not Complete

- NSE market-data integration.
- Paper Trade Validation.
- Intraday profiles.
- Options execution.

Current detailed status remains in [Engine Status](../ENGINE_STATUS.md). Validation evidence remains in [MCX Metals Validation](../validation/MCX-METALS-VALIDATION.md).

## 8. 2026 Roadmap

```text
KRONOS Core Intelligence
  -> MCX Metals Swing (Futures)
  -> MCX Energy Swing (Futures)
  -> NSE Equity Swing (Cash + Futures)
  -> NSE Index Swing (Futures)
  -> Paper Trade Validation
  -> NSE Equity Intraday (Cash + Futures)
  -> NSE Index Intraday (Futures)
  -> KRONOS Platform v1.0
```

## 9. 2027 Vision

The following are future vision items, not commitments and not active development.

### KRONOS Discover

**Status:** Future Vision - Not Active Development

Opportunity Discovery Platform. KRONOS Discover would scan supported markets and surface where the core intelligence engine sees developing opportunity.

### Options Execution Module

**Status:** Future Vision - Not Active Development

An execution module for expressing KRONOS intelligence through supported options strategies after the Cash and Futures modules mature.

### Analytics

**Status:** Future Vision - Not Active Development

A product layer for evaluating completed trades, missed trades, execution quality, performance, and replay evidence.

### Portfolio Intelligence

**Status:** Future Vision - Not Active Development

A portfolio-level intelligence layer for exposure, correlation, concentration, and cross-market risk awareness.

## 10. Deferred Architectural Decisions

Deferred decisions should be resolved through explicit ADLs before implementation changes begin.

- DD-001: Reconcile the preserved legacy Auto CPR mode name after NSE Swing; KES (KRONOS Evidence Synthesis) remains the evidence synthesis boundary.
- DD-002: Execution Profiles from Swing to Intraday after Platform v1.0.
- DD-003: VWAP Evaluation deferred.
- DD-004: Macro Event Engine deferred.

## 11. Platform Success Criteria

### Platform v1.0

Platform v1.0 should be considered successful when:

- MCX Metals, MCX Energy, NSE Equity Swing, and NSE Index Swing have comparable Swing-model maturity where applicable;
- the intelligence engine remains shared across supported market models;
- execution modules remain separate from intelligence ownership;
- KR-390 and KR-400 have sufficient validation evidence for supported model claims;
- documentation, engine status, validation records, and product memory are aligned;
- TradingView compile/runtime behavior is clean for the supported symbol matrix;
- BUY NOW / SELL NOW states and alerts remain explainable and non-automated.

### Platform v2.0

Platform v2.0 should be considered successful when:

- multiple execution modules are formally defined;
- multiple execution profiles are formally defined;
- personal trading layer boundaries are implemented without corrupting KR-390 model-trade ownership;
- analytics and journal workflows use validated trade and replay data;
- market-intelligence expansions are justified by product evidence;
- AI features explain and coach without becoming hidden decision owners.

## 12. Revision History

| Version | Date | Status | Notes |
|---|---|---|---|
| 1.0 | 2026-07-11 | Living Document | Initial canonical product vision and long-term roadmap. |
| 1.1 | 2026-07-11 | Living Document | Documents KRONOS as a market-intelligence platform with multiple execution modules. |

## Canonical References

- [Project Memory](KRONOS_PROJECT_MEMORY.md)
- [Platform Architecture](KRONOS_PLATFORM_ARCHITECTURE.md)
- [Architecture Overview](../architecture/OVERVIEW.md)
- [Engine Ownership](../architecture/ENGINE_OWNERSHIP.md)
- [Data Flow](../architecture/DATA_FLOW.md)
- [Engine Status](../ENGINE_STATUS.md)
- [Roadmap](../../ROADMAP.md)
- [Futures Model ADL](../architecture/ADL-001-Futures-Model.md)
- [MCX Self-Contained Execution ADL](../architecture/ADL-002-MCX-Self-Contained-Execution.md)
- [Execution Context Adapter ADL](../architecture/ADL-003-Execution-Context-Adapters.md)
- [Model Trade Ownership ADL](../architecture/ADL-004-Model-Trade-Ownership.md)
- [Alert Architecture ADL](../architecture/ADL-005-Alert-Architecture.md)
