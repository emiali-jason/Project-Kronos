# DOMAIN-003 — Validation Domain
Status: Approved
Owner: Chief Architect
Version: 1.0

## Purpose

Own Business Judgment by interpreting approved Market Facts and answering what those facts mean for KRONOS business decisions.

## Responsibilities

- Own Business Judgment as the single platform semantic responsibility.
- Consume Market Facts without recreating Observation.
- Publish authoritative business judgment for downstream Risk and Execution consumption.
- Preserve KR-370 ownership of direction and BUY READY / SELL READY within the current KRONOS architecture.

## Non-Responsibilities

- Instrument identity or market-fact production.
- Risk approval.
- Final execution timing, BUY NOW / SELL NOW, or orders.
- Positions or model-trade state.
- Provider integration, market schedules, event transport, runtime configuration, or audit.

## Published Contracts

- Business Judgment Contract — the authoritative business meaning derived from approved Market Facts, including current KR-370 direction and readiness where applicable.

## Consumed Contracts

- Market Facts Contract.

## Architectural Constraints

- Validation answers what the facts mean and must not answer whether risk permits action or whether execution has occurred.
- Validation is the domain-level owner of Business Judgment; existing KR-360 confidence and KR-370 decision responsibilities remain distinct within that domain boundary.
- KR-370 remains the sole current owner of direction and BUY READY / SELL READY.
- Validation must not create BUY NOW / SELL NOW or reinterpret Execution Context.
- Validation evidence does not by itself alter architecture or implementation.

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
