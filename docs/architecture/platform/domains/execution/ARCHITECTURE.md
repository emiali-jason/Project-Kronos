# DOMAIN-004 — Execution Domain
Status: Draft
Owner: Chief Architect

## Purpose

Define the proposed platform boundary for market-neutral execution qualification and final execution timing while preserving existing approved ownership.

## Scope

The Execution Domain organizes the approved relationship between upstream direction and readiness, the applicable Execution Context Provider, and final execution timing.

Execution semantics remain identical across supported markets. Market-specific and product-specific interpretation is encapsulated by the applicable Execution Context Provider and communicated through the approved Execution Context contracts.

## Existing Ownership Preserved

- KR-370 remains upstream and retains direction and BUY READY / SELL READY ownership.
- KR-380A remains the current concrete entry Execution Context Provider within the narrow adapter boundary approved by ADL-003.
- KR-380 remains the sole currently authorized consumer of the entry Execution Context.
- KR-380 retains final execution timing, final execution authorization, and BUY NOW / SELL NOW ownership.
- KR-390A and KR-390 remain outside the entry Execution Context boundary and retain their approved post-entry responsibilities.
- KR-400 alert ownership and KR-705 presentation ownership remain outside final execution timing ownership.

## Provider and Consumer Boundary

An Execution Context Provider may evaluate market-specific and product-specific execution prerequisites and produce standardized execution qualification. It must not own direction, BUY READY, SELL READY, final execution authorization, BUY NOW, SELL NOW, or trade management.

Execution Context consumers depend only on approved public contracts. They do not inspect provider implementation, reconstruct provider interpretation, infer missing context, or reinterpret market-specific rules.

## Boundaries

The Execution Domain does not own:

- instrument identity, classification, or market-data routing;
- evidence generation, observation, validation, confidence, or direction;
- post-entry model-trade management;
- alert delivery or presentation wording;
- broker orders or personal-position state.

The execution lifecycle, payload, and public interface remain governed by their existing approved records. This Draft does not redefine them.

## Open Items

- TODO: Reconcile the approved Execution Context payload document's conceptual and concrete scope before using it as a general platform pattern.
- TODO: Define any missing post-entry public contract through formal architectural review.
- TODO: Define cross-domain dependencies without adding APIs or schemas.

## Related Approved Documents

- [PP-007 — Execution Semantics Across Markets](../../../principles/PP-007-Execution-Semantics-Across-Markets.md)
- [ADR-006 — Execution Context Provider Architecture](../../../adr/ADR-006-Execution-Context-Provider-Architecture.md)
- [ADL-003 — Execution Context Adapters](../../../ADL-003-Execution-Context-Adapters.md)
- [ECIC-001 — Execution Context Interface Contract](../../../interfaces/ECIC-001-Execution-Context-Interface-Contract.md)
- [ECPC-001 — Execution Context Payload Contract](../../../interfaces/ECPC-001-Execution-Context-Payload-Contract.md)
- [ECM-001 — Execution Context Model](../../../models/ECM-001-Execution-Context-Model.md)
- [KRONOS Engine Ownership](../../../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../../../DATA_FLOW.md)
- [PLATFORM-000 — KRONOS Platform Constitution](../../PLATFORM-000-CONSTITUTION.md)
