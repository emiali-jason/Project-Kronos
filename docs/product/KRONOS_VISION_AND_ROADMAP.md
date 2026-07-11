# KRONOS Vision & Roadmap

**Version:** 1.0
**Status:** Living Document

## 1. Vision

KRONOS Futures exists to turn futures trading analysis into a disciplined, explainable, reusable platform. It is being built as a modular intelligence system in Pine Script for TradingView, with one shared engine architecture that can support multiple market models and, later, multiple execution profiles.

KRONOS is not:

- broker automation;
- a black-box AI;
- a signal-selling system.

KRONOS is:

- explainable;
- modular;
- reusable;
- extensible.

The platform should help a trader understand why the market is or is not ready, why execution is or is not allowed, and what objective model trade state KRONOS is tracking after a confirmed trigger. BUY NOW and SELL NOW are confirmed execution-timing states, not broker orders.

## 2. Mission

The long-term mission is to build a professional futures intelligence platform that can support disciplined trading decisions across market models without fragmenting into separate scripts, private logic branches, or opaque signal rules.

KRONOS should preserve trader judgment while reducing confusion. It should organize market evidence, expose blockers, and separate decision, timing, model-trade management, and alerts into clear ownership layers.

## 3. Project North Star

"Build the most disciplined, explainable and reusable futures trading intelligence platform possible using one shared engine architecture across multiple market models and multiple execution profiles."

## 4. Core Design Philosophy

### One Engine, One Responsibility

Every engine answers one question. KR-370 decides direction and readiness. KR-380 decides timing. KR-390 manages the objective model trade. KR-400 owns alert events. KR-705 displays intelligence for the trader.

### Public Output Contracts

Downstream engines should consume stable public `out...` outputs instead of internal variables. This keeps ownership visible and prevents hidden coupling.

### Frozen Modules

Frozen modules should change only through scoped bug fixes, additive compatibility-safe outputs, performance improvements that preserve behavior, or a declared version change.

### Adapter Pattern

Adapters are narrow exceptions. KR-380A and KR-390A may translate minimum lower-level facts that do not yet exist as formal public outputs. They must not duplicate the full intelligence core for Daily, 4H, and 1H.

### Confirmed Bar Finality

Actionable execution states, model-trade starts, model-trade exits, and alert events must respect confirmed-bar finality where applicable.

### MCX Self-contained Execution

The MCX 1H execution chart must explain why the current state is NO TRIGGER, FORMING, BUY NOW, SELL NOW, EXTENDED, or FAILED without forcing the trader to inspect reference charts.

### Model Trade before Personal Trade

KR-390 tracks the objective KRONOS model trade. It does not yet track the user's actual personal position. Personal trade management is a later product layer.

### Explainable Intelligence

KRONOS must show reasons, blockers, and status in trader language. A trader should understand the state without reverse-engineering internal engine names.

### One Engine, Multiple Market Models

Market-specific behavior belongs in dependency profiles, reference symbols, weights, and thresholds. The architecture should not split into separate codebases for metals, energy, and stock futures.

### Future: Multiple Execution Profiles

Current execution profile is Swing. Future execution profiles may include Intraday after Platform v1.0 and model-parity milestones are complete.

## 5. Platform Architecture

```text
Market Models
  ↓
Execution Profiles
  ↓
Shared Intelligence Engines
  ↓
Trader Layer
  ↓
Analytics
  ↓
AI
```

### Market Models

Market Models define what market is being traded and what reference dependencies matter. Current and planned models include MCX Metals, MCX Energy, and NSE Stock Futures.

### Execution Profiles

Execution Profiles define the style and timeframe assumptions for using the same intelligence architecture. The current profile is Swing. Intraday is deferred until after Platform v1.0.

### Shared Intelligence Engines

The shared engines analyze trend, quality, compression, acceptance, momentum, readiness, opportunity, confidence, decisions, execution timing, model trades, and alerts. They should remain generic and reusable.

### Trader Layer

The trader layer is the human-facing interpretation layer. KR-705 is the current panel. It displays public engine outputs and should not own trading decisions.

### Analytics

Analytics will evaluate completed trades, missed trades, execution quality, performance, and replay evidence. This layer is planned after the platform foundations mature.

### AI

The AI layer is future-facing. It may explain, summarize, coach, or brief the trader, but it must not become an opaque decision owner.

## 6. Current Platform Status

### Completed

- Core Platform.
- MCX Metals (Swing).

### In Progress

- MCX Energy (Swing).

### Planned

- NSE Stock Futures (Swing).

### Foundation

- KR-390.
- KR-400.

### Frozen

- Intelligence Core through KR-380.
- KR-705.

Current detailed status remains in [Engine Status](../ENGINE_STATUS.md). Validation evidence remains in [MCX Metals Validation](../validation/MCX-METALS-VALIDATION.md).

## 7. Product Roadmap

### Phase 1

Core Platform Foundation

Completed

--------------------------------

### Phase 2

Market Models

MCX Metals (Swing)

Completed

↓

MCX Energy (Swing)

Next

↓

NSE Stock Futures (Swing)

Next

--------------------------------

### Phase 3

KRONOS Platform v1.0

Platform Freeze

Documentation Phase 3

Final Validation

--------------------------------

### Phase 4

Execution Profiles

Swing

↓

Intraday

Initially:

- Nifty Futures
- Bank Nifty Futures
- NSE Stock Futures

Later:

- MCX Metals
- MCX Energy

--------------------------------

### Phase 5

Personal Trading Layer

Examples:

- Position Manager
- Manual Entry Confirmation
- Position Sizing
- Portfolio Exposure

--------------------------------

### Phase 6

Trader Intelligence

Examples:

- Journal
- Performance Analytics
- Missed Trades
- Execution Score
- Replay

--------------------------------

### Phase 7

Market Intelligence

Examples:

- Macro Event Engine
- OPEC
- Weather
- EIA
- Volume Profile
- VWAP evaluation (only if justified)

--------------------------------

### Phase 8

AI Layer

Examples:

- AI Coaching
- Trade Review
- Daily Briefing
- Portfolio Assistant

## 8. Deferred Architectural Decisions

### DD-001

Rename

Auto KGS

↓

Market Structure Engine

Target:

After NSE Swing

### DD-002

Execution Profiles

Swing

↓

Intraday

Target:

After Platform v1.0

### DD-003

VWAP Evaluation

Deferred

### DD-004

Macro Event Engine

Deferred

Deferred decisions should be resolved through explicit ADLs before implementation changes begin.

## 9. Platform Success Criteria

### Platform v1.0

Platform v1.0 should be considered successful when:

- MCX Metals, MCX Energy, and NSE Stock Futures have comparable Swing-model maturity where applicable;
- frozen core ownership through KR-380 remains intact;
- KR-390 and KR-400 have sufficient validation evidence for supported model claims;
- documentation, engine status, validation records, and product memory are aligned;
- TradingView compile/runtime behavior is clean for the supported symbol matrix;
- BUY NOW / SELL NOW states and alerts remain explainable and non-automated.

### Platform v2.0

Platform v2.0 should be considered successful when:

- multiple execution profiles are formally defined;
- personal trading layer boundaries are implemented without corrupting KR-390 model-trade ownership;
- analytics and journal workflows use validated trade and replay data;
- market-intelligence expansions such as macro events or VWAP are justified by product evidence;
- AI features explain and coach without becoming hidden decision owners.

## 10. Revision History

| Version | Date | Status | Notes |
|---|---|---|---|
| 1.0 | 2026-07-11 | Living Document | Initial canonical product vision and long-term roadmap. |

## Canonical References

- [Project Memory](KRONOS_PROJECT_MEMORY.md)
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
