# Execution Engineering Component
Status: Draft
Owner: Chief Architect

## Purpose

Translate DOMAIN-004 — Execution into one primary Execution engineering component while preserving market-neutral execution semantics and the approved Execution Context boundary.

## Platform Domain Trace

- Exactly one domain: [DOMAIN-004 — Execution](ARCHITECTURE.md).

## Engineering Responsibility

Realize approved execution action and order semantics while preserving KR-380 ownership of final execution timing and BUY NOW / SELL NOW.

## Responsibilities

- Consume approved Business Judgment and Risk Approval.
- Preserve KR-380 final execution timing and authorization ownership.
- Consume standardized Execution Context only through the approved ADR-006, ECIC-001, ECPC-001, and ECM-001 boundary.
- Publish the approved Execution Outcome Contract and Order Contract.

## Explicit Non-Responsibilities

- Instrument Identity, Market Facts, Business Judgment, direction, BUY READY / SELL READY, Risk Approval, positions, model-trade management, external provider integration, Market Schedule, Runtime Configuration, Platform Events, or Audit Trail.
- Market-specific execution logic or broker-order placement under the current contract.

## Consumed Approved Contracts

- Business Judgment Contract.
- Risk Approval Contract.
- Execution Context Contract as an approved platform-support contract.

## Published Approved Contracts

- Execution Outcome Contract.
- Order Contract.

## Allowed Dependencies

- Business-domain dependencies: Validation and Risk only.
- Platform support: the approved Execution Context boundary; this does not add a business-domain dependency.

## Prohibited Dependencies

- Direct business-domain dependencies on Instrument, Observation, or Portfolio.
- Provider-component internals or external-provider meaning as a substitute for Execution Context.
- Any Execution Context consumer other than the currently authorized KR-380 without a separate approved architecture decision.

## Existing KR Engine Alignment

- KR-380 retains final execution timing and BUY NOW / SELL NOW ownership.
- KR-380A remains the current concrete entry Execution Context Provider in its narrow approved role.
- KR-390 and KR-390A remain Portfolio-aligned post-entry model-trade responsibilities.

## Existing Implementation Alignment

- KR-380A and KR-380 sections exist in `KRONOS_FUTURES/source/KRONOS_FUTURES.pine`.
- BUY NOW and SELL NOW remain confirmed timing states, not broker orders.
- No independently packaged Execution component or broker-order implementation was discovered.

## Open Engineering Questions

- How will the future Risk Approval Contract be made available before Execution integration without changing KR-380 ownership?
- Which existing KR-380 outputs conform to the Execution Outcome Contract while preserving current timing-state semantics?
