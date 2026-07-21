# DOMAIN-001 — Instrument Domain
Status: Draft
Owner: Chief Architect

## Purpose

Define the proposed platform boundary for instrument identity, classification, and configured relationships while preserving existing engine ownership.

## Scope

The Instrument Domain organizes the architectural meaning of:

- market, exchange, symbol, and instrument identity;
- asset and market-model classification;
- analysis, reference, and execution instrument distinctions;
- configured relationships between an instrument and its applicable market references;
- support and routing intent before market-data retrieval.

## Existing Ownership Preserved

- KR-200 retains market, exchange, symbol, and instrument identity responsibilities.
- KR-250 retains asset-to-reference mapping and dependency-profile responsibilities.
- KR-251 retains market-model classification and analysis/execution instrument semantics.
- KR-252 retains configured market-relationship responsibilities.
- KR-260A retains standardized symbol-routing responsibilities.

This domain grouping does not merge those responsibilities or authorize one owner to recreate another owner's outputs.

## Boundaries

The Instrument Domain does not own:

- market-data retrieval or normalization;
- indicator or evidence calculation;
- observation or validation conclusions;
- confidence, direction, or readiness;
- Execution Context qualification or final execution timing;
- trade management, alerts, or presentation.

Instrument classification must not change the meaning of BUY READY, SELL READY, BUY NOW, or SELL NOW. Market-specific execution semantics remain governed by PP-007 and the approved Execution Context architecture.

## Open Items

- TODO: Define the approved Instrument Domain information catalogue.
- TODO: Define the approved lifecycle and ownership of instrument information.
- TODO: Review cross-domain dependencies without introducing schemas or interfaces.

## Related Approved Documents

- [ADL-001 — Futures Model Architecture](../../../ADL-001-Futures-Model.md)
- [KRONOS Engine Ownership](../../../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../../../DATA_FLOW.md)
- [PP-007 — Execution Semantics Across Markets](../../../principles/PP-007-Execution-Semantics-Across-Markets.md)
- [PLATFORM-000 — KRONOS Platform Constitution](../../PLATFORM-000-CONSTITUTION.md)
