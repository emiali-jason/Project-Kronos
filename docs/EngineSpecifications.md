# KRONOS Engine Specifications

**Status:** Specification index
**Date:** 2026-07-10

This document is the canonical index for engine specifications. It does not duplicate the full current engine registry. Use [Engine Status](ENGINE_STATUS.md) for current source metadata and [Engine Ownership](architecture/ENGINE_OWNERSHIP.md) for responsibility boundaries.

## Purpose

Engine specifications define the stable contract for each KRONOS engine or adapter:

- what question it answers;
- what it owns;
- what it consumes;
- what it exposes;
- what it must not do;
- how it is validated.

Detailed specifications should be written only when the engine's responsibility is stable enough to document without constant churn.

## Required Specification Template

Every detailed engine specification should include:

| Field | Required content |
|---|---|
| Engine number/name | KR number and canonical engine title. |
| Question answered | The single question the engine owns. |
| Responsibility | What the engine is allowed to decide or calculate. |
| Inputs | Public outputs and any approved direct data interfaces. |
| Outputs | Public outputs, states, text, readiness flags, and compatibility aliases. |
| State model | Numeric states, text states, exclusivity rules, and readiness behavior. |
| Confirmed-bar behavior | Whether outputs are intrabar, confirmed-only, or mixed. |
| Adapter use | Whether the engine uses or provides an adapter exception. |
| Downstream consumers | Engines, panels, or alert systems that consume its outputs. |
| Frozen contract | Change policy, compatibility rules, and ownership boundaries. |
| Validation evidence | Static, compile, visual, replay, or live evidence. |
| Known limitations | Simplifications, unsupported conditions, or future work. |

## Implemented Engine and Adapter Index

| Engine | Role | Current maturity | Source/status links | Detailed spec needed? |
|---|---|---|---|---|
| KR-280 | CPR Intelligence Engine | FROZEN | [Status](ENGINE_STATUS.md), [Ownership](architecture/ENGINE_OWNERSHIP.md) | Yes |
| KR-300 | Trend Foundation Engine | FROZEN | [Status](ENGINE_STATUS.md), [Ownership](architecture/ENGINE_OWNERSHIP.md) | Yes |
| KR-310 | Trend Quality Engine | FROZEN | [Status](ENGINE_STATUS.md), [Ownership](architecture/ENGINE_OWNERSHIP.md) | Yes |
| KR-315 | Compression Intelligence Engine | FROZEN | [Status](ENGINE_STATUS.md), [Ownership](architecture/ENGINE_OWNERSHIP.md) | Yes |
| KR-320 | Market Acceptance Engine | FROZEN | [Status](ENGINE_STATUS.md), [Ownership](architecture/ENGINE_OWNERSHIP.md) | Yes |
| KR-330 | Momentum Confirmation Engine | FROZEN | [Status](ENGINE_STATUS.md), [Ownership](architecture/ENGINE_OWNERSHIP.md) | Yes |
| KR-340 | Review Readiness Engine | FROZEN | [Status](ENGINE_STATUS.md), [Ownership](architecture/ENGINE_OWNERSHIP.md) | Yes |
| KR-350 | Opportunity Foundation Engine | FROZEN | [Status](ENGINE_STATUS.md), [Ownership](architecture/ENGINE_OWNERSHIP.md) | Yes |
| KR-360 | Confidence Engine | FROZEN | [Status](ENGINE_STATUS.md), [Ownership](architecture/ENGINE_OWNERSHIP.md) | Yes |
| KR-370 | Decision Engine | FROZEN | [Status](ENGINE_STATUS.md), [Ownership](architecture/ENGINE_OWNERSHIP.md) | Yes |
| KR-380A | Execution Context Adapter | FROZEN adapter | [Status](ENGINE_STATUS.md), [Ownership](architecture/ENGINE_OWNERSHIP.md), [ADL-003](architecture/ADL-003-Execution-Context-Adapters.md) | Yes |
| KR-380 | Execution Trigger Engine | FROZEN | [Status](ENGINE_STATUS.md), [Ownership](architecture/ENGINE_OWNERSHIP.md) | Yes |
| KR-390A | Trade Management Execution Adapter | FOUNDATION adapter | [Status](ENGINE_STATUS.md), [Ownership](architecture/ENGINE_OWNERSHIP.md), [ADL-004](architecture/ADL-004-Model-Trade-Ownership.md) | Yes |
| KR-390 | Trade Management Engine | FOUNDATION | [Status](ENGINE_STATUS.md), [Ownership](architecture/ENGINE_OWNERSHIP.md) | Yes, after live validation matures |
| KR-400 | Execution Alert Engine | FOUNDATION | [Status](ENGINE_STATUS.md), [Ownership](architecture/ENGINE_OWNERSHIP.md), [ADL-005](architecture/ADL-005-Alert-Architecture.md) | Yes, after alert validation matures |
| KR-705 | Engine Status Panel | FROZEN trader display | [Status](ENGINE_STATUS.md), [Ownership](architecture/ENGINE_OWNERSHIP.md) | Yes |

## Specification Policy

- Do not invent public outputs not verified in source or canonical documentation.
- Do not copy volatile source details into this index.
- Write detailed specs in separate files when they are needed for implementation or review.
- A frozen module's detailed spec must match its source header and frozen contract.
- Foundation modules may have provisional specs, clearly labeled as such.

## Cross-References

- [Architecture Overview](architecture/OVERVIEW.md)
- [Engine Ownership](architecture/ENGINE_OWNERSHIP.md)
- [Data Flow](architecture/DATA_FLOW.md)
- [Engine Status](ENGINE_STATUS.md)
- [Testing Protocol](validation/TESTING.md)
- [MCX Metals Validation](validation/MCX-METALS-VALIDATION.md)
