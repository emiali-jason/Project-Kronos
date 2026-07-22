# Market Engineering Component
Status: Draft
Owner: Chief Architect

## Purpose

Translate DOMAIN-008 — Market into one primary Market engineering component while preserving explicit-source requirements for market schedule and availability.

## Platform Domain Trace

- Exactly one domain: [DOMAIN-008 — Market](ARCHITECTURE.md).

## Engineering Responsibility

Realize approved Market Schedule ownership and publish explicit market availability only when an approved authoritative source exists.

## Responsibilities

- Preserve the separation between Market Schedule, market-data availability, and Execution Context validity.
- Preserve KR-200’s existing EAIC-001 producer responsibility.
- Publish only the approved Market Schedule Contract and EAIC-001 Exchange Availability Contract.

## Explicit Non-Responsibilities

- Instrument Identity, Market Facts, Business Judgment, Risk Approval, execution timing, orders, positions, provider integration, Runtime Configuration, Platform Events, or Audit Trail.
- Inferring OPEN or CLOSED from stale data, missing bars, readiness, or execution failure.

## Consumed Approved Contracts

- None from the business pipeline.

## Published Approved Contracts

- Market Schedule Contract.
- EAIC-001 Exchange Availability Contract.

## Allowed Dependencies

- Business-domain dependencies: None.

## Prohibited Dependencies

- Any business-domain dependency.
- Using market-data availability, Execution Context, or execution state as a market-schedule source.
- Allowing Market output to alter KR-370, KR-380, alerts, trade management, or data readiness.

## Existing KR Engine Alignment

- KR-200 retains EAIC-001 production only when an approved authoritative source exists.
- KR-200’s Instrument Identity responsibility remains separately aligned to the Instrument component.
- KR-705 may present EAIC-001 output but must not infer it.

## Existing Implementation Alignment

- KR-200 market and instrument identification exists in `KRONOS_FUTURES/source/KRONOS_FUTURES.pine`.
- No EAIC-001 publication or authoritative Market Schedule source was discovered in the current Pine source.
- No independently packaged Market component exists.

## Open Engineering Questions

- What approved authoritative source will support Market Schedule and EAIC-001 publication?
- Which KR-200 public output will carry the approved availability meaning once such a source exists?
