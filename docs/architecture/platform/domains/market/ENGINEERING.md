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

- Which KR-200 public output will carry the approved availability meaning once such a source exists?

## WO-06MCX-A Contract-Family Expiry-Session Authority

DOMAIN-008 publishes
`KRONOS-MCX-CONTRACT-FAMILY-SESSION-V1 / 1` through the immutable
`KRONOS-MCX-CONTRACT-FAMILY-EXPIRY-SESSIONS-2026 / 2026.1.0`
publication. The publication binds official MCX contract specifications for
GOLDM, SILVERM, COPPER, NATURALGAS and CRUDEOIL, plus the explicit governed
consumer aliases NATGAS and CRUDE. Alias resolution is exact; fuzzy family
matching is prohibited.

The contract distinguishes `PRE_EXPIRY_SESSION`,
`EXPIRY_SESSION_BEFORE_CUTOFF`, `EXPIRY_SESSION_AFTER_CUTOFF` and
`POST_EXPIRY`. At the exact published expiry close, the contract is still
expiry-day eligible; eligibility ends strictly after that instant. This
eligibility fact does not select an active contract.

The current family rules retain each specification's own authority:

- GOLDM, SILVERM, NATURALGAS and CRUDEOIL use the governed normal MCX session
  on their expiry date.
- COPPER uses the governed normal session before expiry and a 17:00 Asia/Kolkata
  close on expiry, as expressly stated in the MCX Copper specification.

The derived expiry schedule is a completed-candle boundary. It never extends
an expiring COPPER contract to the generic 23:30 close. Unknown families,
uncovered calendar dates, contract expiries outside a source-effective period,
missing expiry sessions, missing publications and invalid digests raise the
typed `MCX_CONTRACT_SESSION_UNAVAILABLE` boundary. Generic MCX hours are not a
fallback.

Historical replay binds the requested contract family, expiry, trading date,
historical observation instant, publication version and digest. Later source
changes require an immutable successor publication and cannot rewrite the
2026 record.

DOMAIN-008 supplies session authority only. The separately governed WO-06MCX
resolver owns active-contract selection; Intraday Discovery and Probables own
neither authority.
