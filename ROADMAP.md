# Project KRONOS Roadmap

**Status:** Canonical roadmap
**Date:** 2026-07-10

This roadmap describes the current path for KRONOS Futures. Detailed engine status lives in [Engine Status](docs/ENGINE_STATUS.md), and supported-model evidence lives in [MCX Metals Validation](docs/validation/MCX-METALS-VALIDATION.md).

## Current Completed Foundation

Current supported model:

- MCX Metals: Gold, Silver, Copper.
- Reference mappings: Gold -> `COMEX:GC1!`, Silver -> `COMEX:SI1!`, Copper -> `COMEX:HG1!`.
- Execution context: MCX 1H.

Completed architecture foundation:

- MCX Metals futures-to-futures reference model.
- One-engine-one-responsibility architecture.
- Public-output contracts between engines.
- Narrow adapter pattern for execution and trade-management context.
- MCX self-contained execution rule.
- Frozen intelligence, decision, and execution core through KR-380.
- KR-390 Trade Management Foundation.
- KR-400 Alert Foundation.
- KR-705 frozen trader-facing display layer.

## Immediate Next Milestones

1. Complete and live-validate KR-390 Trade Management.
2. Complete and live-validate KR-400 Execution Alerts.
3. Extend the Futures Model to MCX Energy:
   - Crude Oil;
   - Natural Gas.
4. Extend the Futures Model to NSE Stock Futures.

Validation must follow the [Testing Protocol](docs/validation/TESTING.md). Current MCX Metals evidence is tracked in [MCX Metals Validation](docs/validation/MCX-METALS-VALIDATION.md).

## Model-Parity Milestone

Before expanding into broader platform capabilities, the supported futures models should reach comparable maturity through KR-390 and KR-400 where applicable:

- MCX Metals;
- MCX Energy;
- NSE Stock Futures.

Model parity means each market model has documented reference dependencies, execution constraints, validation scope, and known limitations. It does not require identical thresholds or identical market behavior.

## Later Capability Layers

After model parity, KRONOS may expand into:

- position management for actual user trades;
- risk and sizing;
- visualization and dashboard improvements;
- scanner workflows;
- trade journal support;
- analytics;
- AI explanation;
- platform services.

These are later capability layers. They should not be assigned engine numbers until their ownership and architecture are documented.

## Aspirational Work

Longer-term possibilities include richer cross-market intelligence, portfolio-level insight, user workflow automation, and deeper analytics. These remain aspirational until formally designed.

## Current Non-Goals

For the current phase, KRONOS does not target:

- options;
- broker automation;
- portfolio automation;
- a full AI layer.

## Architecture References

- [Architecture Overview](docs/architecture/OVERVIEW.md)
- [Engine Ownership](docs/architecture/ENGINE_OWNERSHIP.md)
- [Data Flow](docs/architecture/DATA_FLOW.md)
- [Futures Model ADL](docs/architecture/ADL-001-Futures-Model.md)
- [MCX Self-Contained Execution ADL](docs/architecture/ADL-002-MCX-Self-Contained-Execution.md)
