# DOMAIN-007 — Risk Domain
Status: Approved
Owner: Chief Architect
Version: 1.2

## Purpose

Own the authoritative decision of whether an approved Business Judgment is allowed given the applicable Portfolio State.

## Responsibilities

- Own Risk Approval as the single platform semantic responsibility.
- Consume Business Judgment and the previously established Portfolio State.
- Publish permission or refusal for Execution without changing the underlying judgment.
- Keep risk permission distinct from execution timing and position ownership.

## Non-Responsibilities

- Instrument identity, Market Facts, or Business Judgment.
- KR-370 analytical promotion, KR-380 entry timing/Entry Outcomes, or orders.
- Positions or Portfolio State.
- Provider integration, market schedules, platform events, runtime configuration, or audit.

## Published Contracts

- Risk Approval Contract — the authoritative permission decision consumed by Execution.
- Swing V1 Risk Permission Contract — `KRONOS-SWING-DOMAIN-007-RISK-PERMISSION-V1`, commissioned by ADR-0013 for objective entry-timing permission only.

## Consumed Contracts

- Business Judgment Contract.
- Portfolio State Contract.

## Architectural Constraints

- Risk answers whether action is allowed and must not answer what happened, what it means, or whether execution occurred.
- Risk must not recreate Validation judgment or Portfolio state.
- Risk permission alone must produce neither KR-370 analytical promotion nor a KR-380 Entry Outcome.
- No current engine responsibility is silently reassigned by this domain-level approval.
- Swing V1 V1 introduces no quantity, allocation, margin, leverage, concentration, correlation, drawdown, or R:R threshold. Missing authoritative Portfolio State produces `UNAVAILABLE`.
- Current Risk Permission is bound to one exact Step-31 plan and Portfolio State cycle and is invalid after either is superseded.

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
