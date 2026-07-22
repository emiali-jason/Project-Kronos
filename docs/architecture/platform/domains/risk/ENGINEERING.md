# Risk Engineering Component
Status: Draft
Owner: Chief Architect

## Purpose

Translate DOMAIN-007 — Risk into one primary Risk engineering component without changing current KR engine responsibilities.

## Platform Domain Trace

- Exactly one domain: [DOMAIN-007 — Risk](ARCHITECTURE.md).

## Engineering Responsibility

Realize approved Risk Approval ownership by deciding whether an approved Business Judgment is allowed given the previously established Portfolio State.

## Responsibilities

- Consume the approved Business Judgment Contract and Portfolio State Contract.
- Preserve both consumed meanings without recreating Validation or Portfolio logic.
- Publish only the approved Risk Approval Contract.
- Keep risk permission distinct from execution timing and position ownership.

## Explicit Non-Responsibilities

- Instrument Identity, Market Facts, Business Judgment, execution timing, BUY NOW / SELL NOW, orders, Positions, Portfolio State, provider integration, Market Schedule, Platform Events, Runtime Configuration, or Audit Trail.
- Producing execution outcomes or assigning a new responsibility to an existing KR engine.

## Consumed Approved Contracts

- Business Judgment Contract.
- Portfolio State Contract.

## Published Approved Contracts

- Risk Approval Contract.

## Allowed Dependencies

- Business-domain dependencies: Validation and Portfolio only.

## Prohibited Dependencies

- Direct business-domain dependencies on Instrument, Observation, or Execution.
- Access to Validation or Portfolio internals rather than their approved contracts.
- Feedback that makes Risk the owner of business judgment, positions, or execution timing.

## Existing KR Engine Alignment

- No current engine is silently reassigned to own the approved Risk Approval responsibility.
- KR-390 remains Portfolio-aligned objective model-trade state even where KR-705 currently displays it in a row labelled Risk.
- KR-380 remains Execution-aligned final timing and is not the Risk component.

## Existing Implementation Alignment

- No dedicated Risk Approval engine or independently packaged Risk component was discovered.
- Current Pine model-trade risk references remain KR-390 Portfolio responsibilities and do not implement DOMAIN-007 Risk Approval.

## Open Engineering Questions

- What approved rules will define Risk Approval without transferring Validation or Portfolio ownership?
- How will previous Portfolio State be identified across decision cycles without creating circular authority?
- What evidence is required before this currently unimplemented component can advance beyond Draft?
