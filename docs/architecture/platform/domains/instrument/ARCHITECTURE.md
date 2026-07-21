# DOMAIN-001 — Instrument Domain
Status: Approved
Owner: Chief Architect
Version: 1.0

## Purpose

Own the canonical business meaning of instrument identity so every downstream domain refers to the same instrument, market identity, classification, and approved analysis/reference/execution relationship.

## Responsibilities

- Own Instrument Identity as the single platform semantic responsibility.
- Define the distinction between analysis instruments, reference instruments, and execution instruments.
- Preserve the approved identity, mapping, classification, relationship, and routing responsibilities currently assigned to KR-200, KR-250, KR-251, KR-252, and KR-260A.
- Publish instrument meaning without performing market observation or business judgment.

## Non-Responsibilities

- Market facts or evidence.
- Business judgment, direction, or BUY READY / SELL READY.
- Risk approval.
- Execution timing, BUY NOW / SELL NOW, or orders.
- Positions, model-trade state, provider integration, market schedules, events, runtime configuration, or audit.

## Published Contracts

- Instrument Identity Contract — the authoritative semantic identity and classification of the instrument and its approved analysis/reference/execution relationships.

## Consumed Contracts

- None from another business domain.
- Platform-supplied values may support identification but do not own or alter Instrument Identity.

## Architectural Constraints

- Instrument begins the business pipeline and has no business-domain dependency.
- Instrument Identity must have one semantic owner even when current engine responsibilities remain distributed.
- Instrument classification must not change the meaning of KR-370 or KR-380 states.
- Approved analysis and execution instrument distinctions in ADL-001 remain preserved.

## Approved Constitutional References

- CA-013 — Domain Identity
- CA-014 — Responsibility Classes
- CA-015 — Contract-Based Dependencies
- CA-016 — Single Semantic Ownership
- CA-017 — Domain Communication (Platform Only)
- CA-018 — Human Workflow Independence
- CA-019 — Architecture Freeze
- [PLATFORM-000 — KRONOS Platform Constitution](../../PLATFORM-000-CONSTITUTION.md)
- [Platform Business Pipeline](../../PLATFORM_BUSINESS_PIPELINE.md)
- [Domain Dependency Matrix](../../DOMAIN_DEPENDENCY_MATRIX.md)
- [Domain Ownership Matrix](../../DOMAIN_OWNERSHIP_MATRIX.md)

## Related Approved Repository Documents

- [ADL-001 — Futures Model Architecture](../../../ADL-001-Futures-Model.md)
- [KRONOS Engine Ownership](../../../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../../../DATA_FLOW.md)
- [PP-007 — Execution Semantics Across Markets](../../../principles/PP-007-Execution-Semantics-Across-Markets.md)
