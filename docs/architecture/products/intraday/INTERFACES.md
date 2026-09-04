# Intraday Interfaces

**Status:** Living interface index
**Owner:** KRONOS Intraday

## Interfaces Provided

- `KRONOS-INTRADAY-NATIVE-UNIVERSE-V1` publication.
- `IntradayUniverseResolution` for per-member canonical/runtime availability.
- Intraday factual, validation, persistence, route, and view contracts already
  published by Slices 0–3 and WO-02.
- `KRONOS-INTRADAY-WO16-SPONSOR-DECISION-SNAPSHOT-V1`,
  `KRONOS-INTRADAY-WO16-SPONSOR-DECISION-V1`, and
  `KRONOS-INTRADAY-WO16-LIFECYCLE-ADMISSION-V1` after their separately
  authorized source implementation.
- `KRONOS-INTRADAY-WO17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-MONITORING-V1`
  after separately authorized production-contract implementation.
- `KRONOS-INTRADAY-OPERATIONAL-READINESS-REVIEW-V1` immutable read-only
  composition snapshots after WO-B1 publication.

## Interfaces Consumed

- DOMAIN-001 `RuntimeInstrumentRegistry` and canonical catalogue.
- DOMAIN-006 authenticated read-only Provider lease.
- DOMAIN-008 market calendar/schedule facts.
- Product-neutral persistence, audit, notification, and Browser seams where
  explicitly governed.
- Exact current WO-13 Trade Plan, WO-14 Risk Observation, WO-15 Timing Handoff
  and session binding, DOMAIN-008 session fact, and canonical
  subject/Instrument/contract/roll lineage for WO-16.
- Exact WO-13/14/15/16 lineage, DOMAIN-008 session facts and canonical
  subject/Instrument/contract/roll lineage for WO-17.
- Shared DOMAIN-006 read-only Kite WebSocket transport for active WO-17
  monitoring without sharing Swing product state.
- Exact immutable references to Probables, analytical promotion, WO-13,
  WO-14, WO-15, WO-16, WO-17, DOMAIN-001 and DOMAIN-008 producer artifacts for
  future WO-B composition; WO-B1 executes none of those producers.

## Interface Ownership

Producers retain semantic ownership. Consumption does not permit Intraday to
read producer internals or overwrite canonical, Provider, Market, or Risk facts.

## Authoritative Cross-Product Contracts

See the Platform Architecture Index and the Intraday Living Architecture Record.

## Governing ADRs

The Intraday Shared-File Change Rule governs cross-product implementation seams.
