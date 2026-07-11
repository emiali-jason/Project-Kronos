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
- NSE Equity Swing
- NSE Index Swing

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

## Model: NSE Equity Swing and NSE Index Swing

**Markets:** Approved 91-stock NSE cash universe, NIFTY, BANKNIFTY

**Dependencies:**

- Underlying cash stock
- NIFTY
- Sector index
- Relative strength

**Profile:** LocalMarketRelative

NSE Swing instruments are primarily local-market-relative. KRONOS should evaluate NSE Equity Swing through the relationship between the cash stock, intended stock-futures execution instrument, benchmark index, sector context, and relative strength. KRONOS should evaluate NSE Index Swing through the cash index and intended index-futures execution instrument.

## Design Decision

The Futures Model selector is a configuration layer, not a separate engine family. It must not split KRONOS into separate codebases for metals, energy, and stock futures. Each model should adapt how the same generic KRONOS engines interpret market dependencies.

Auto detection may be added later, but manual model override must remain available for validation, edge cases, and trader preference.

## Amendment - 2026-07-10

This amendment updates implementation status and current dependency mappings without replacing the original decision.

### Current MCX Metals References

The current validated futures-to-futures mappings are:

| MCX execution asset | Current reference symbol |
|---|---|
| Gold | `COMEX:GC1!` |
| Silver | `COMEX:SI1!` |
| Copper | `COMEX:HG1!` |

For the current implementation, these mappings supersede the original MCX Metals dependency references to XAUUSD and XAGUSD. The original text remains above as historical design context.

### Implementation Status

- **MCX Metals:** Currently supported for Gold, Silver, and Copper.
- **MCX Energy:** Configuration supported for Crude Oil and Natural Gas Swing; market-data integration remains pending.
- **NSE Equity Swing:** Configuration supported for the approved 91-stock cash universe; market-data integration remains pending.
- **NSE Index Swing:** Configuration supported for `NSE:NIFTY` and `NSE:BANKNIFTY`; market-data integration remains pending.
- **Futures Model selector:** Planned and not yet implemented as a user-facing selector.

The current absence of the selector does not change the architecture decision. Market-specific configuration must remain a profile layer over common engines.

### Self-Contained Execution

The MCX 1H execution chart must be self-contained. Reference Daily, 4H, and 1H markets provide supporting context, but they do not execute MCX trades. Confirmed BUY NOW and SELL NOW events may occur only on the MCX 1H execution chart.

The panel must translate all remaining reference and execution blockers into trader-readable requirements on that chart. See [ADL-002](ADL-002-MCX-Self-Contained-Execution.md).

### Adapter-Based Dependency Translation

Market-model dependencies must be translated through narrow, documented adapters where a safe public interface does not yet exist. An adapter may expose minimum execution facts; it must not duplicate complete Daily, 4H, or 1H intelligence stacks.

KR-380A and KR-390A are the current formal adapter examples. See [ADL-003](ADL-003-Execution-Context-Adapters.md).

### Manual Override

When the Futures Model selector is implemented, manual override remains required for validation, edge cases, symbol-recognition failures, contract changes, and trader preference. Auto detection must never be the only route to a model profile.

### Execution Semantics

The configuration layer distinguishes analysis symbols from intended execution instruments:

- MCX Metals and MCX Energy analyse futures and execute futures.
- NSE Equity Swing analyses the cash stock and describes execution as the corresponding stock future, such as `RELIANCE FUT`. No expiring monthly futures symbol is generated.
- NSE Index Swing analyses the cash index (`NSE:NIFTY` or `NSE:BANKNIFTY`) and describes execution as `NIFTY FUT` or `BANKNIFTY FUT`. No expiring monthly futures symbol is generated.

This closes configuration semantics only. KR-260A must still connect market-data retrieval before NSE Swing can be considered operational.
