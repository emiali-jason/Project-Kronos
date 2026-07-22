# Validation Engineering Component
Status: Draft
Owner: Chief Architect

## Purpose

Translate DOMAIN-003 — Validation into one primary Validation engineering component without merging KR-360 and KR-370 responsibilities.

## Platform Domain Trace

- Exactly one domain: [DOMAIN-003 — Validation](ARCHITECTURE.md).

## Engineering Responsibility

Realize the approved Business Judgment responsibility by interpreting approved Market Facts and publishing their authoritative business meaning.

## Responsibilities

- Consume only the approved Market Facts Contract from Observation.
- Preserve distinct confidence and decision responsibilities within Validation.
- Preserve KR-370 ownership of direction and BUY READY / SELL READY.
- Publish only the approved Business Judgment Contract.

## Explicit Non-Responsibilities

- Instrument Identity, Market Facts production, Risk Approval, final execution timing, BUY NOW / SELL NOW, orders, positions, provider integration, Market Schedule, event transport, Runtime Configuration, or Audit Trail.
- Reinterpreting Execution Context or producing an execution outcome.

## Consumed Approved Contracts

- Market Facts Contract.

## Published Approved Contracts

- Business Judgment Contract.

## Allowed Dependencies

- Business-domain dependencies: Observation only.

## Prohibited Dependencies

- Direct business-domain dependencies on Instrument, Risk, Execution, or Portfolio.
- Access to Observation internals rather than the Market Facts Contract.
- Any direct dependency inferred from a transitive relationship.

## Existing KR Engine Alignment

- KR-360 retains confidence ownership.
- KR-370 retains direction, readiness, and BUY READY / SELL READY ownership.
- Component alignment does not merge the two engine responsibilities.

## Existing Implementation Alignment

- KR-360 and KR-370 sections exist in `KRONOS_FUTURES/source/KRONOS_FUTURES.pine`.
- No independently packaged Validation component exists; current behavior remains within the production Pine source.

## Open Engineering Questions

- Which current KR-360 and KR-370 public outputs collectively conform to the Business Judgment Contract?
- What contract-conformance evidence is required without changing KR-370’s public states or current engine ownership?
