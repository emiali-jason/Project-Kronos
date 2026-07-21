# DOMAIN-004 — Execution Domain
Status: Approved
Owner: Chief Architect
Version: 1.0

## Purpose

Own execution action and order semantics while preserving KR-380 final execution timing and the market-neutral Execution Context architecture.

## Responsibilities

- Own Orders as the single platform semantic responsibility.
- Consume approved Business Judgment and Risk Approval.
- Preserve KR-380 ownership of final execution timing, final execution authorization, and BUY NOW / SELL NOW.
- Consume standardized Execution Context only through the approved provider and interface boundaries.
- Publish the completed Execution Outcome for Portfolio.

## Non-Responsibilities

- Instrument identity or market facts.
- Business Judgment, direction, or BUY READY / SELL READY.
- Risk Approval.
- Positions or post-entry model-trade management.
- Provider integration, market schedules, runtime configuration, platform event semantics, or audit.

## Published Contracts

- Execution Outcome Contract — the authoritative completed execution result made available to Portfolio.
- Order Contract — the sole platform meaning of an order; the current KRONOS contract does not place broker orders.

## Consumed Contracts

- Business Judgment Contract.
- Risk Approval Contract.
- Execution Context Contract as an approved platform-support contract governed by ADR-006, ECIC-001, ECPC-001, and ECM-001.

## Architectural Constraints

- KR-380 remains the sole currently authorized consumer of the entry Execution Context.
- KR-380A remains the current concrete entry Execution Context Provider within ADL-003's narrow boundary.
- Execution Context Providers must not own direction, readiness, final execution authorization, BUY NOW / SELL NOW, orders, or positions.
- Execution semantics remain identical across markets under PP-007.
- BUY NOW and SELL NOW remain confirmed timing states and are not broker orders.

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

- [PP-007 — Execution Semantics Across Markets](../../../principles/PP-007-Execution-Semantics-Across-Markets.md)
- [ADR-006 — Execution Context Provider Architecture](../../../adr/ADR-006-Execution-Context-Provider-Architecture.md)
- [ADL-003 — Execution Context Adapters](../../../ADL-003-Execution-Context-Adapters.md)
- [ECIC-001 — Execution Context Interface Contract](../../../interfaces/ECIC-001-Execution-Context-Interface-Contract.md)
- [ECPC-001 — Execution Context Payload Contract](../../../interfaces/ECPC-001-Execution-Context-Payload-Contract.md)
- [ECM-001 — Execution Context Model](../../../models/ECM-001-Execution-Context-Model.md)
- [KRONOS Engine Ownership](../../../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../../../DATA_FLOW.md)
