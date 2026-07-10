# ADL-002 - MCX Self-Contained Execution

**Status:** Approved
**Date:** 2026-07-10

## Context

MCX Metals depend on global reference markets for direction, acceptance, compression, and momentum context. Requiring the trader to inspect separate COMEX Daily, 4H, and 1H charts merely to understand an MCX execution blocker would make the workflow fragmented and error-prone.

Reference charts support the execution decision, but they are not the local execution venue.

## Decision

**The MCX execution chart must always be self-contained.**

For the current MCX Metals model:

- reference Daily, 4H, and 1H provide supporting context;
- MCX 1H is the only executable chart;
- BUY NOW and SELL NOW may occur only on confirmed MCX 1H context;
- the MCX 1H panel must show the highest-priority remaining blockers;
- the trader must not need to open a reference chart to learn why execution is pending.

## Supporting Reference Markets

| MCX execution asset | Reference market |
|---|---|
| Gold | `COMEX:GC1!` |
| Silver | `COMEX:SI1!` |
| Copper | `COMEX:HG1!` |

Reference charts may be used for diagnostics and validation. They cannot emit executable MCX BUY NOW/SELL NOW states because they do not satisfy the MCX 1H execution gate.

## Blocker Translation

Internal blocker sources may identify the originating context, such as reference Daily direction, reference 4H acceptance/compression, reference 1H momentum, or MCX 1H readiness.

KR-705 must present those facts in trader-readable terms, for example:

- Waiting for trend alignment;
- Waiting for breakout;
- Waiting for price acceptance;
- Momentum needs to strengthen;
- Price is extended.

The display should communicate the required market behavior without exposing implementation-oriented engine names.

## Ownership

- KR-370 decides direction and readiness.
- KR-380A translates narrow reference and execution facts.
- KR-380 decides execution timing.
- KR-705 displays and translates the result.

Self-containment does not authorize KR-380 or KR-705 to recreate the intelligence core.

## Scaling to Other Futures Models

### MCX Energy

The same rule will apply when the Energy model is approved: NYMEX/Brent/currency references support the decision, while the MCX execution chart remains self-contained. Energy-specific blockers must be translated through a model profile or narrow adapter rather than by cloning engines.

### NSE Stock Futures

The execution chart should similarly contain the actionable result while underlying cash, index, sector, and relative-strength references remain supporting dependencies.

## Consequences

Benefits:

- one operational chart for execution;
- explicit separation between reference evidence and execution venue;
- fewer missed blockers;
- a consistent panel contract across future market models.

Costs:

- adapters and blocker translation require disciplined public interfaces;
- validation must cover both the supporting references and the execution chart;
- internal blocker detail must remain precise even when display wording is simplified.

## Relationship to Earlier Assumptions

This decision supersedes the old DD-004 assumption that each timeframe must provide a separate trader workflow and that 4H/1H execution intelligence could remain unavailable until separate full engines existed. Separate charts remain useful for diagnostics; they are no longer required for the trader to understand MCX execution readiness.

See [ADL-003](ADL-003-Execution-Context-Adapters.md) and [Data Flow](DATA_FLOW.md).
