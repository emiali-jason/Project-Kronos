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

## Prospective programme V2 successor authority

**Status:** Approved for bounded engineering under [ADR-0039](../../adr/ADR-0039-INTRADAY-PROSPECTIVE-WO09-WO16-PROGRAMME-AUTHORITY.md).

The preceding historical epoch remains readable, not a concurrent prospective
owner. Current sequence: WO09 readiness → WO10 Futures construction/Risk/selection
→ WO11 lifecycle → WO12 research/XLSX → WO13 notifications → WO14 journal
→ WO15 portfolio → WO16 reports. Later work orders are not implemented here.
See [WO10 interface](KRONOS-INTRADAY-WO-10-FUTURES-INTERFACE-V1.md) and
[historical compatibility](KRONOS-INTRADAY-HISTORICAL-WORK-ORDER-COMPATIBILITY.md).

## WO-10 successor ownership — ADR-0040

**Status:** Approved bounded engineering, Sponsor / EA 2026-09-11.

Native owns prospective structural selection, exact sources and target completeness. WO-10 consumes approved retained authority; missing authority persists as TRADE_PLAN_UNAVAILABLE without demoting 5/5 readiness. No new Native selector is authorized; production positive commissioning remains unresolved. Trade Candidates is the Sponsor home for WO-10 and future WO-11. Primary navigation is Opportunities, Review, Trade Candidates, Active, Closed; historical WO deep links remain. Active/Closed grant no lifecycle authority.


## Prospective Native PULLBACK V1 successor

[Native structural selection policy V1](KRONOS-INTRADAY-NATIVE-STRUCTURAL-SELECTION-POLICY-V1.md), governed by ADR-0041, commissions PULLBACK-only selection and contract 1.1.0. Native owns exact roles/cycle and typed target completeness; WO-10 consumes immutable positive/NOT_ESTABLISHED decisions. BREAKOUT stays uncommissioned; earlier contracts and records remain preserved. Positive monetary execution permission still requires existing explicit Risk and instrument economics authority, never inferred defaults.

## Final WO-10 Futures / advisory Risk — ADR-0042

Status: Approved bounded engineering, direct Sponsor / EA 2026-09-11.

[ADR-0042](../../adr/ADR-0042-WO10-ADVISORY-RISK-AND-FINAL-FUTURES-COMPOSITION.md) supersedes prospective Risk permission with advisory facts/reference/quantity warnings. No Risk magnitude or missing monetary fact independently vetoes Sponsor selection. Native PULLBACK V1, five-tab navigation, exact trade hard gates and historical contracts remain preserved. No WO11 lifecycle, broker margin, production operation or runtime load is commissioned.
