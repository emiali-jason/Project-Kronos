# DOMAIN-006 — Provider Domain
Status: Approved
Owner: Chief Architect
Version: 1.0

## Purpose

Own integration with external providers while preventing provider-specific concerns from acquiring business meaning or domain authority.

## Responsibilities

- Own Provider Integration as the single platform semantic responsibility.
- Represent provider capability and availability without creating Market Facts or Business Judgment.
- Isolate provider-specific concerns from business-domain semantics.
- Publish provider-support information only through approved platform contracts.

## Non-Responsibilities

- Instrument Identity or Market Facts.
- Business Judgment, Risk Approval, execution timing, orders, or positions.
- Market Schedule, runtime configuration, platform event semantics, or audit.
- The Execution Context Provider responsibility defined by ADR-006 solely because both use the word provider.

## Published Contracts

- Provider Integration Contract — the authoritative platform meaning of provider capability and provider availability.

## Consumed Contracts

- None from the business pipeline.

## Architectural Constraints

- Provider has no business judgment dependency.
- Provider-specific meaning must not leak into business contracts.
- Business domains must not depend on provider internals.
- The ADR-006 Execution Context Provider remains an Execution-domain role and is not reassigned to Provider.

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

- [ADR-006 — Execution Context Provider Architecture](../../../adr/ADR-006-Execution-Context-Provider-Architecture.md)
- [ADL-003 — Execution Context Adapters](../../../ADL-003-Execution-Context-Adapters.md)
- [KRONOS Engine Ownership](../../../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../../../DATA_FLOW.md)
