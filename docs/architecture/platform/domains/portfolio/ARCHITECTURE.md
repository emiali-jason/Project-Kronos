# DOMAIN-005 — Portfolio Domain
Status: Approved
Owner: Chief Architect
Version: 1.0

## Purpose

Own the authoritative position and portfolio state that answers what KRONOS owns after a completed Execution Outcome.

## Responsibilities

- Own Positions as the single platform semantic responsibility.
- Consume completed Execution Outcomes.
- Publish Portfolio State for later Risk decisions.
- Preserve KR-390 ownership of the objective KRONOS model trade within the current architecture.

## Non-Responsibilities

- Instrument identity, market facts, or Business Judgment.
- Risk Approval.
- Execution timing, BUY NOW / SELL NOW, or orders.
- Provider integration, market schedules, platform events, runtime configuration, or audit.
- Broker automation or unapproved personal broker-position tracking.

## Published Contracts

- Portfolio State Contract — the authoritative state of positions and portfolio ownership.
- Objective Model Trade Contract — the current KR-390 model-trade state within the approved non-broker boundary.

## Consumed Contracts

- Execution Outcome Contract.

## Architectural Constraints

- Portfolio must not reinterpret the completed Execution Outcome.
- Risk may consume the previously established Portfolio State, but Portfolio must not produce Risk Approval.
- KR-390's objective model trade remains independent of whether a person entered a trade.
- No personal broker-position ownership is introduced by this document.

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

- [ADL-004 — Model Trade Ownership](../../../ADL-004-Model-Trade-Ownership.md)
- [KRONOS Engine Ownership](../../../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../../../DATA_FLOW.md)
