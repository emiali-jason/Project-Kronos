# Intraday Interfaces

**Status:** Living interface index
**Owner:** KRONOS Intraday

## Interfaces Provided

- `KRONOS-INTRADAY-NATIVE-UNIVERSE-V1` publication.
- `IntradayUniverseResolution` for per-member canonical/runtime availability.
- Intraday factual, validation, persistence, route, and view contracts already
  published by Slices 0–3 and WO-02.

## Interfaces Consumed

- DOMAIN-001 `RuntimeInstrumentRegistry` and canonical catalogue.
- DOMAIN-006 authenticated read-only Provider lease.
- DOMAIN-008 market calendar/schedule facts.
- Product-neutral persistence, audit, notification, and Browser seams where
  explicitly governed.

## Interface Ownership

Producers retain semantic ownership. Consumption does not permit Intraday to
read producer internals or overwrite canonical, Provider, Market, or Risk facts.

## Authoritative Cross-Product Contracts

See the Platform Architecture Index and the Intraday Living Architecture Record.

## Governing ADRs

The Intraday Shared-File Change Rule governs cross-product implementation seams.
