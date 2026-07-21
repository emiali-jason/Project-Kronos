# DOMAIN-007 — Risk Domain
Status: Approved
Owner: Chief Architect
Version: 1.0

## Purpose

Own the authoritative decision of whether an approved Business Judgment is allowed given the applicable Portfolio State.

## Responsibilities

- Own Risk Approval as the single platform semantic responsibility.
- Consume Business Judgment and the previously established Portfolio State.
- Publish permission or refusal for Execution without changing the underlying judgment.
- Keep risk permission distinct from execution timing and position ownership.

## Non-Responsibilities

- Instrument identity, Market Facts, or Business Judgment.
- Execution timing, BUY NOW / SELL NOW, or orders.
- Positions or Portfolio State.
- Provider integration, market schedules, platform events, runtime configuration, or audit.

## Published Contracts

- Risk Approval Contract — the authoritative permission decision consumed by Execution.

## Consumed Contracts

- Business Judgment Contract.
- Portfolio State Contract.

## Architectural Constraints

- Risk answers whether action is allowed and must not answer what happened, what it means, or whether execution occurred.
- Risk must not recreate Validation judgment or Portfolio state.
- Risk permission alone must not produce BUY NOW / SELL NOW.
- No current engine responsibility is silently reassigned by this domain-level approval.

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
