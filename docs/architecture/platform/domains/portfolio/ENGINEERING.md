# Portfolio Engineering Component
Status: Draft
Owner: Chief Architect

## Purpose

Translate DOMAIN-005 — Portfolio into one primary Portfolio engineering component while preserving the objective, non-broker KRONOS model-trade boundary.

## Platform Domain Trace

- Exactly one domain: [DOMAIN-005 — Portfolio](ARCHITECTURE.md).

## Engineering Responsibility

Realize approved Positions ownership by consuming completed Execution Outcomes and publishing authoritative Portfolio State.

## Responsibilities

- Consume only the approved Execution Outcome Contract.
- Preserve KR-390 ownership of the objective KRONOS model trade.
- Publish the approved Portfolio State Contract and Objective Model Trade Contract.
- Preserve model state independently of undocumented human or broker action.

## Explicit Non-Responsibilities

- Instrument Identity, Market Facts, Business Judgment, Risk Approval, execution timing, BUY NOW / SELL NOW, orders, provider integration, Market Schedule, Platform Events, Runtime Configuration, or Audit Trail.
- Personal broker-position tracking, broker automation, or reinterpretation of a completed Execution Outcome.

## Consumed Approved Contracts

- Execution Outcome Contract.

## Published Approved Contracts

- Portfolio State Contract.
- Objective Model Trade Contract.

## Allowed Dependencies

- Business-domain dependencies: Execution only.

## Prohibited Dependencies

- Direct business-domain dependencies on Instrument, Observation, Validation, or Risk.
- Access to Execution internals rather than the Execution Outcome Contract.
- Producing Risk Approval or changing completed execution meaning.

## Existing KR Engine Alignment

- KR-390 retains objective model-trade entry, state, stops, targets, and lifecycle ownership.
- KR-390A retains its narrow post-entry trade-management adapter role.
- KR-380 remains the owner of the upstream confirmed execution-timing outcome.

## Existing Implementation Alignment

- KR-390A and KR-390 sections exist in `KRONOS_FUTURES/source/KRONOS_FUTURES.pine`.
- No personal-position or broker-fill implementation exists.
- No independently packaged Portfolio component exists.

## Open Engineering Questions

- Which current KR-390 public outputs collectively conform to the Portfolio State and Objective Model Trade contracts?
- How will future Portfolio State be exposed to Risk without creating circular authority in one business decision cycle?
