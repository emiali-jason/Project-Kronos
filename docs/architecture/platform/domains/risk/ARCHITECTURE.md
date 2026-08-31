# DOMAIN-007 — Risk Domain
Status: Approved
Owner: Chief Architect
Version: 1.4

## Purpose

Own authoritative Risk semantics under exact product-specific contracts: Risk
permission where explicitly commissioned and advisory loss-exposure observation
where explicitly commissioned.

## Responsibilities

- Own Risk Approval and Risk Observation as distinct, explicitly versioned
  DOMAIN-007 semantic responsibilities.
- Consume only the facts required by the exact product contract.
- Publish permission/refusal only under a permission contract; publish no
  permission under an observation contract.
- Keep Risk semantics distinct from geometry, execution timing, Sponsor choice
  and position ownership.

## Non-Responsibilities

- Instrument identity, Market Facts, or Business Judgment.
- KR-370 analytical promotion, KR-380 entry timing/Entry Outcomes, or orders.
- Positions or Portfolio State.
- Provider integration, market schedules, platform events, runtime configuration, or audit.

## Published Contracts

- Risk Approval Contract — the authoritative permission decision consumed by Execution.
- Swing V1 Risk Permission Contract — `KRONOS-SWING-DOMAIN-007-RISK-PERMISSION-V1`, commissioned by ADR-0013 for objective entry-timing permission only.
- Intraday V1 Risk Observation Contract — `KRONOS-INTRADAY-DOMAIN-007-RISK-OBSERVATION-V1`, commissioned by ADR-0023 for advisory loss-exposure observation only; it grants no permission and creates no veto.

## Consumed Contracts

- Business Judgment Contract.
- Portfolio State Contract.

## Architectural Constraints

- Risk answers only the question authorized by the exact product contract. It
  must not translate permission and observation state families.
- Risk must not recreate Validation judgment or Portfolio state.
- Risk permission alone must produce neither KR-370 analytical promotion nor a KR-380 Entry Outcome.
- No current engine responsibility is silently reassigned by this domain-level approval.
- Swing V1 V1 introduces no quantity, allocation, margin, leverage, concentration, correlation, drawdown, or R:R threshold. Missing authoritative Portfolio State produces `UNAVAILABLE`.
- Current Risk Permission is bound to one exact Step-31 plan and Portfolio State cycle and is invalid after either is superseded.

## Observation-Phase Conformance

[ADR-0015](../../../adr/ADR-0015-SWING-SPONSOR-OBSERVATION-PHASE-AUTHORITY-AND-STEP-31-EVIDENCE-GOVERNANCE.md)
does not make DOMAIN-007 advisory. `REJECTED` and `UNAVAILABLE` remain genuine
hard blockers at every objective-timing, Sponsor-position, or other activation
boundary that requires current Risk permission. Missing, stale, mismatched, or
integrity-invalid Risk and Portfolio State bindings remain fail closed.

`APPROVED` and `CONSTRAINED` permit objective timing only and do not become a
Sponsor recommendation. Risk reason, constraint, and availability facts may be
presented and retained as observation evidence, but no DOMAIN-007 state itself
records `LIVE`, `PAPER`, or `IGNORE`. A Step-31 geometry warning alone is not a
DOMAIN-007 result and must not be interpreted as the Sponsor's decision.

[ADR-0016](../../../adr/ADR-0016-SWING-PAPER-OBSERVATION-TRACK-AUTHORITY.md)
does not weaken this boundary. A blocked `PAPER` decision may later have a
separately identified Paper Observation Track only as non-position research
evidence. The Track receives no Risk approval, override, or bypass, and cannot
create a Sponsor Position or objective activation. It preserves the immutable
decision-time Risk result as evidence.

## Intraday Product Conformance

[ADR-0023](../../../adr/ADR-0023-INTRADAY-DOMAIN-007-ADVISORY-RISK-OBSERVATION-BOUNDARY.md)
creates an explicit product-specific successor contract for Intraday only.
Intraday WO-14 reports factual loss exposure and availability through
`RISK_OBSERVED`, `RISK_ALERT` and `RISK_UNAVAILABLE`. Those states are advisory
and cannot approve, reject, block or bypass progression to WO-15. Sponsor owns
participation and actual quantity; WO-13 owns immutable geometry; WO-15 owns
final 5M timing.

This product-specific contract does not weaken, supersede or reinterpret the
Swing permission contract or the general Risk Approval Contract. A consumer
must bind the exact product contract and may not translate states between the
Swing and Intraday families.

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
