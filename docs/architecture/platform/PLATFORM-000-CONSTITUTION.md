# PLATFORM-000 — KRONOS Platform Constitution
Status: Draft
Owner: Chief Architect

## Purpose

Define the proposed constitutional baseline for KRONOS Platform architecture without replacing or reinterpreting existing approved repository documents.

This document remains non-authoritative until formal review and approval by the Chief Architect.

## Authority Boundary

- Existing approved Architecture Decision Records, approved interface contracts, approved platform governance, and canonical ownership and data-flow documents remain authoritative within their recorded scope.
- This Draft does not approve PP-001 through PP-006, assign implementation authority, or supersede an existing approved decision.
- A conflict between this Draft and an approved repository document must be resolved in favor of the approved document until a new decision is formally approved.

## Platform Constraints

1. Each architectural responsibility has one explicit owner.
2. Evidence production, observation, validation, confidence, decision, execution, trade management, alerts, and presentation remain distinct responsibilities.
3. Evidence engines do not make trading decisions.
4. KR-370 retains ownership of direction and BUY READY / SELL READY.
5. KR-380 retains ownership of final execution timing and BUY NOW / SELL NOW.
6. Market-specific execution interpretation remains encapsulated by the applicable Execution Context Provider and does not move into execution authorization components.
7. Execution Context communication remains standardized, deterministic, immutable for an evaluation cycle, and independent of provider implementation.
8. Consumers do not reconstruct provider logic, infer missing context, or bypass approved public contracts.
9. Analysis instruments, reference instruments, and execution instruments remain architecturally distinct where existing approved records distinguish them.
10. Observation and validation precede any approved integration into confidence or decision responsibilities.
11. Architecture changes require a recorded architectural decision and must preserve approved consumer responsibilities.

## Domain Boundary Rule

Platform domains organize related architectural responsibilities. A domain document does not transfer, merge, or replace engine ownership recorded in ENGINE_OWNERSHIP or information flow recorded in DATA_FLOW.

Cross-domain communication must preserve the producing owner's authority and the consuming owner's responsibility. A shared concept does not create shared ownership.

## Change Control

Changes to an approved platform constraint, ownership boundary, or cross-domain contract require formal architectural review and an approved decision record.

Draft domain documents may identify open questions and TODOs but must not create implementation authority.

## Open Items

- TODO: Formal review of this constitutional baseline.
- TODO: Formal review of domain ownership and cross-domain dependencies.
- TODO: Formal review of PP-001 through PP-006.
- TODO: Definition and approval of platform Information Objects and their lifecycle.

## Related Approved Documents

- [KRONOS Platform Governance](../../product/PLATFORM_GOVERNANCE.md)
- [KRONOS Engine Ownership](../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../DATA_FLOW.md)
- [PP-007 — Execution Semantics Across Markets](../principles/PP-007-Execution-Semantics-Across-Markets.md)
- [ADR-006 — Execution Context Provider Architecture](../adr/ADR-006-Execution-Context-Provider-Architecture.md)
- [ADL-003 — Execution Context Adapters](../ADL-003-Execution-Context-Adapters.md)
