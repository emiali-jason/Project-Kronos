# KRONOS Platform Architecture

**Status:** Product Architecture
**Date:** 2026-07-11

## Purpose

This document describes KRONOS from a product perspective rather than an engineering perspective.

KRONOS is the platform. KRONOS Core is the current shared intelligence product. Products and execution modules consume KRONOS Core intelligence; they do not implement independent trading logic.

## Product Architecture

```text
KRONOS Core
  -> Execution Modules
       - Cash
       - Futures
       - Options (Future)
  -> KRONOS Discover (Future)
  -> KRONOS Analytics (Future)
```

## KRONOS Core

KRONOS Core is the shared intelligence product. It analyzes market evidence and produces explainable BUY/SELL decisions, readiness states, blockers, timing states, model-trade state, and alert events.

The execution chart is the trader's primary interface, but BUY READY and SELL READY are reserved for the final consolidated multi-timeframe KRONOS decision. Local execution-timeframe evidence may support WATCH LONG, WATCH SHORT, SETUP BUILDING, WAIT, or AVOID, but final READY states require the consolidated directional contract.

The core intelligence engine should remain reusable across market models and execution modules.

## Execution Modules

Execution modules decide how a KRONOS intelligence decision can be expressed for a specific instrument.

Current execution modules:

- Cash
- Futures

Future execution modules:

- Options (not currently implemented)

Examples:

| Instrument | Analysis | Execution |
|---|---|---|
| RELIANCE | NSE Cash | Cash + Futures |
| 3M INDIA | NSE Cash | Cash Only |
| NIFTY | NSE Index | Futures |
| MCX GOLD | MCX Futures | Futures |

The BUY/SELL signal does not change because the execution vehicle changes.

## Consolidated Directional Contract

KR-341 owns the authoritative Weekly/Daily/4H directional bias for swing-trading decisions. KR-300 remains the Daily trend foundation engine; it does not attempt to represent the complete multi-timeframe decision. KR-360 and KR-370 consume KR-341 where directional authority is required, while KR-380 continues to own execution timing only.

Weekly Neutral is permissive in this contract. READY permission requires Confirmed Daily direction and aligned 4H structure; Developing Daily may support WATCH behaviour but must not authorize BUY READY or SELL READY. Neutral and Conflicted are separate states so the trader and future review tools can distinguish incomplete alignment from direct timeframe contradiction.

## KRONOS Discover

**Status:** Future Vision - Not Active Development

KRONOS Discover is a future opportunity discovery product. It may scan supported markets and surface developing opportunities using the same KRONOS Core outputs.

## KRONOS Analytics

**Status:** Future Vision - Not Active Development

KRONOS Analytics is a future product layer for performance review, execution quality, missed trades, replay evidence, and portfolio intelligence.

## Product Boundary

Products consume KRONOS Core intelligence. They do not implement independent trading logic.

Execution modules may change how a decision is expressed, but they must not create separate BUY/SELL logic outside the intelligence engine.

## Compatibility Naming

The repository and Pine filename may retain historical `KRONOS_FUTURES` naming until a separately approved migration. Runtime identifiers and public compatibility names remain unchanged. Historical references should not be rewritten when they accurately describe the project at that time.

## Governance References

- [Versioning Policy](VERSIONING_POLICY.md)
- [Release Policy](RELEASE_POLICY.md)
- [Platform Governance](PLATFORM_GOVERNANCE.md)
