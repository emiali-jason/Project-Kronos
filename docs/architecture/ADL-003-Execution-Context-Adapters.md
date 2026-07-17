# ADL-003 - Execution Context Adapters

**Status:** Approved
**Date:** 2026-07-10

## Context

KRONOS normally requires downstream engines to consume public outputs from prior engines. Execution timing and trade management occasionally require a narrow confirmed fact that is not exposed by an existing intelligence contract.

Duplicating the complete intelligence core for Daily, 4H, and 1H would increase script size, create inconsistent rules, and weaken ownership boundaries.

## Decision

**Narrow adapters may bridge low-level market data into execution engines without duplicating complete intelligence stacks.**

An adapter is an explicit, documented exception to strict prior-engine-output-only access. It may expose only the minimum fact required by its consumer.

## Authority Alignment

The approved entry Execution Context architecture is governed by:

- [ADR-006](adr/ADR-006-Execution-Context-Provider-Architecture.md) for provider and consumer ownership, execution topology, and execution responsibility boundaries;
- [ECIC-001](interfaces/ECIC-001-Execution-Context-Interface-Contract.md) for the public Execution Context interface;
- [ECM-001](models/ECM-001-Execution-Context-Model.md) for Execution Context lifecycle and behavior; and
- [ECPC-001](interfaces/ECPC-001-Execution-Context-Payload-Contract.md) for conceptual payload governance and payload-validation obligations.

This ADL does not define or modify those responsibilities, guarantees, behaviors, or payload decisions. It retains authority only for the narrow lower-level data-access exception, adapter-local access limits and safety, and adapter responsibilities outside the entry Execution Context boundary.

## Current Adapter Exceptions

| Adapter | ADL-owned exception | Narrow source access | Governing boundary |
|---|---|---|---|
| KR-380A | Narrow lower-level data access required by the current concrete entry Execution Context Provider | Selected KR-260/270 reference Daily, 4H, 1H and MCX execution facts, plus established public direction/readiness context | Provider and consumer ownership and topology: ADR-006. Public interface: ECIC-001. Behavior: ECM-001. Payload governance: ECPC-001. |
| KR-390A | Trade Management Execution Adapter serving the existing KR-390 management path; may expose execution close, prior-five-completed-bar swing low/high, context readiness, and stop readiness | MCX 1H execution H/L/C and MCX execution-context readiness | Outside ADR-006's current entry Execution Context boundary. Existing trade-management ownership remains defined by Engine Ownership and Data Flow. |

## Allowed Scope

An adapter may:

- read a narrowly identified lower-level dataset;
- calculate a small factual condition required by one consumer;
- use completed-bar indexing when the contract requires confirmed structure;
- translate model dependencies into a stable public contract governed by the applicable architecture authority.

For KR-380A, ECPC-001 exclusively governs payload concepts and payload-validation obligations. This ADL authorizes only the narrow source-access exception and does not authorize additional payload content.

## Prohibited Scope

An adapter must not:

- duplicate KR-300 through KR-370 across multiple timeframes;
- recreate trend, quality, compression, acceptance, momentum, opportunity, confidence, or decision scoring;
- expose broad raw datasets merely for convenience;
- become an undocumented path around an approved public contract;
- absorb or redefine responsibilities assigned by ADR-006, Engine Ownership, Data Flow, or another approved architecture document.

Entry Execution Context Provider prohibitions and execution-engine responsibilities are defined exclusively by ADR-006. This ADL does not restate or modify them.

## Public Contract Rule

For KR-380A, ECIC-001 is the sole authority for the public Execution Context interface and ECPC-001 is the sole authority for conceptual payload governance. This ADL defines neither the interface nor the payload.

For KR-390A and adapter exceptions outside ADR-006's current entry boundary, the consumer must use the adapter's documented public outputs rather than its internal calculations. Other engines must not reach through an adapter to its low-level source data.

Any additional entry Execution Context consumer requires the separate approved architecture decision required by ADR-006. This ADL does not authorize additional consumers.

## Confirmed-Bar Safety

KR-380A evaluation-cycle behavior and confirmed-data boundaries are governed exclusively by ECM-001.

KR-390A excludes the current execution bar from its swing reference. Existing KR-390 model-trade state-transition and managed-stop responsibilities remain defined by Engine Ownership, Data Flow, and their applicable approved architecture.

Adapter-local calculations permitted by this ADL must not use lookahead or future-confirmed values.

## Consequences

The adapter pattern keeps the intelligence core generic and prevents three full timeframe-specific copies. The cost is that every exception must be documented, small, validated, visible in the ownership registry, and subordinate to its governing ownership, interface, behavior, and payload authorities.

## Related Documents

- [ADR-006 — Execution Context Provider Architecture](adr/ADR-006-Execution-Context-Provider-Architecture.md)
- [ECIC-001 — Execution Context Interface Contract](interfaces/ECIC-001-Execution-Context-Interface-Contract.md)
- [ECM-001 — Execution Context Model](models/ECM-001-Execution-Context-Model.md)
- [ECPC-001 — Execution Context Payload Contract](interfaces/ECPC-001-Execution-Context-Payload-Contract.md)
- [PP-007 — Execution Semantics Across Markets](principles/PP-007-Execution-Semantics-Across-Markets.md)
- [Engine Ownership](ENGINE_OWNERSHIP.md)
- [Data Flow](DATA_FLOW.md)
- [ADL-002 — MCX Self-Contained Execution](ADL-002-MCX-Self-Contained-Execution.md)

## Alignment History

| Date | Change | Responsibility impact |
|---|---|---|
| 2026-07-17 | Aligned entry Execution Context references with approved ADR-006, ECIC-001, ECM-001, and ECPC-001; removed duplicated entry execution definitions. | None. The narrow-access exception and responsibilities outside the entry Execution Context boundary are preserved. |
