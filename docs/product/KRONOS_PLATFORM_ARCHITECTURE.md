# KRONOS Platform Architecture

**Status:** Product Architecture
**Date:** 2026-07-11

## Purpose

This document describes KRONOS from a product perspective rather than an engineering perspective.

KRONOS is a market-intelligence platform. Products and execution modules consume the KRONOS Intelligence Engine. They do not implement independent trading logic.

## Product Architecture

```text
KRONOS Core Intelligence
  -> Execution Modules
       - Cash
       - Futures
       - Options (Future)
  -> KRONOS Discover (Future)
  -> KRONOS Analytics (Future)
```

## KRONOS Core Intelligence

KRONOS Core Intelligence is the shared decision layer. It analyzes market evidence and produces explainable BUY/SELL decisions, readiness states, blockers, timing states, model-trade state, and alert events.

The core intelligence engine should remain reusable across market models and execution modules.

## Execution Modules

Execution modules decide how a KRONOS intelligence decision can be expressed for a specific instrument.

Current execution modules:

- Cash
- Futures

Future execution modules:

- Options

Examples:

| Instrument | Analysis | Execution |
|---|---|---|
| RELIANCE | NSE Cash | Cash + Futures |
| 3M INDIA | NSE Cash | Cash Only |
| NIFTY | NSE Index | Futures |
| MCX GOLD | MCX Futures | Futures |

The BUY/SELL signal does not change because the execution vehicle changes.

## KRONOS Discover

**Status:** Future Vision - Not Active Development

KRONOS Discover is a future opportunity discovery product. It may scan supported markets and surface developing opportunities using the same KRONOS Core Intelligence outputs.

## KRONOS Analytics

**Status:** Future Vision - Not Active Development

KRONOS Analytics is a future product layer for performance review, execution quality, missed trades, replay evidence, and portfolio intelligence.

## Product Boundary

Products consume the KRONOS Intelligence Engine. They do not implement independent trading logic.

Execution modules may change how a decision is expressed, but they must not create separate BUY/SELL logic outside the intelligence engine.
