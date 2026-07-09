# ADL-001 — Futures Model Architecture

**Status:** Approved for Version 1.x, not required for initial MVP  
**Date:** 2026-07-09

## Context

KRONOS Futures must support different futures models through a main Futures Model selector rather than separate codebases. The system should remain one analytical platform while allowing market-specific dependency profiles, reference symbols, weights, and thresholds to adapt the interpretation layer.

## Architectural Principle

**One Engine. Multiple Market Models.**

KRONOS analytical engines remain generic. Market-specific behavior is controlled by dependency profiles, reference symbols, weights, and thresholds. Manual override must remain available even if Auto detection is added.

## Planned Futures Model Selector

- Auto
- MCX Metals
- MCX Energy
- NSE Stock Futures

## Model: MCX Metals

**Markets:** Gold, Silver, Copper

**Dependencies:**

- COMEX
- XAUUSD
- XAGUSD
- COMEX Copper
- USDINR
- MCX execution

**Profile:** GlobalDominant

MCX Metals are globally driven markets where international reference pricing, currency conversion, and local execution behavior must be interpreted together. KRONOS should treat global price discovery as dominant while preserving MCX-specific execution context.

## Model: MCX Energy

**Markets:** Crude Oil, Natural Gas

**Dependencies:**

- NYMEX Crude
- NYMEX Natural Gas
- Brent
- USDINR

**Profile:** GlobalEventDriven

MCX Energy markets are highly sensitive to global event flow, inventory data, geopolitical developments, and international benchmark movement. KRONOS should allow this model to weight global event-driven references more heavily than local-only behavior.

## Model: NSE Stock Futures

**Markets:** NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, individual stock futures

**Dependencies:**

- Underlying cash stock
- NIFTY
- Sector index
- Relative strength

**Profile:** LocalMarketRelative

NSE Stock Futures are primarily local-market-relative instruments. KRONOS should evaluate them through the relationship between the futures contract, underlying cash instrument, benchmark index, sector context, and relative strength.

## Design Decision

The Futures Model selector is a configuration layer, not a separate engine family. It must not split KRONOS into separate codebases for metals, energy, and stock futures. Each model should adapt how the same generic KRONOS engines interpret market dependencies.

Auto detection may be added later, but manual model override must remain available for validation, edge cases, and trader preference.
