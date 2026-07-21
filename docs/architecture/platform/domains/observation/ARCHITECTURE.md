# DOMAIN-002 — Observation Domain
Status: Approved
Owner: Chief Architect
Version: 1.0

## Purpose

Own the authoritative publication of market facts that answer what happened, without creating business judgment, risk permission, or execution authority.

## Responsibilities

- Own Market Facts as the single platform semantic responsibility.
- Publish observations derived by the existing evidence owners without transferring or duplicating their engine responsibilities.
- Preserve the distinction between observed evidence and evidence approved for downstream influence.
- Make market facts available to Validation through the approved contract boundary.

## Non-Responsibilities

- Instrument identity.
- Business judgment, confidence ownership, direction, or BUY READY / SELL READY.
- Risk approval.
- Execution timing, BUY NOW / SELL NOW, or orders.
- Positions, provider integration, market schedules, runtime configuration, or audit conclusions.

## Published Contracts

- Market Facts Contract — authoritative observed facts available for business interpretation.

## Consumed Contracts

- Instrument Identity Contract.

## Architectural Constraints

- Observation answers what happened and must not answer what it means.
- Source engines retain their existing ENGINE_OWNERSHIP responsibilities.
- Observational evidence must not influence KR-370 or KR-380 unless an approved downstream contract authorizes that influence.
- Human display or review does not change the authority of an observation.

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

- [KRONOS Platform Governance](../../../../product/PLATFORM_GOVERNANCE.md)
- [KRONOS Engine Ownership](../../../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../../../DATA_FLOW.md)
