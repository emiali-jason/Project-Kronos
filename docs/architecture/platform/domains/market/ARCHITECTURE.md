# DOMAIN-008 — Market Domain
Status: Approved
Owner: Chief Architect
Version: 1.0

## Purpose

Own the authoritative semantic meaning of market schedules and explicit market availability without inferring them from unrelated data or execution state.

## Responsibilities

- Own Market Schedule as the single platform semantic responsibility.
- Publish explicit market schedule or availability meaning only when an approved authoritative source exists.
- Preserve the separation between market schedule, market-data availability, and Execution Context validity.
- Preserve KR-200's existing EAIC-001 producer responsibility.

## Non-Responsibilities

- Instrument Identity or Market Facts.
- Business Judgment, Risk Approval, execution timing, orders, or positions.
- Provider integration, runtime configuration, platform event semantics, or audit.
- Inference of market status from stale data, missing bars, readiness, or execution failure.

## Published Contracts

- Market Schedule Contract — the authoritative platform meaning of applicable market schedule.
- EAIC-001 Exchange Availability Contract — the current approved presentation-facing availability meaning.

## Consumed Contracts

- None from the business pipeline.

## Architectural Constraints

- Market has no business judgment dependency.
- OPEN and CLOSED may be published only under EAIC-001 and only from an approved authoritative source.
- Exchange Availability must not alter KR-370, KR-380, Execution Context, alerts, trade management, or data readiness.
- KR-200's Instrument Identity and Market Schedule responsibilities remain semantically separate even where one engine currently publishes both.

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

- [EAIC-001 — Exchange Availability Interface Contract](../../../interfaces/EAIC-001-Exchange-Availability-Interface-Contract.md)
- [KRONOS Engine Ownership](../../../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../../../DATA_FLOW.md)
