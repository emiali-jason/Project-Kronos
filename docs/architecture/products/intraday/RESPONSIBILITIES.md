# Intraday Responsibilities

**Status:** Living boundary record
**Owner:** KRONOS Intraday

## Approved Responsibilities

- Govern the versioned 98-member Native analytical universe.
- Own Intraday factual composition, product policy, state, persistence identity,
  validation records, notification projection, journal, and Browser routes.
- Preserve unavailable members without inventing canonical or Provider facts.
- Fail closed per member when required runtime evidence is unavailable.

## Ownership Boundaries

DOMAIN-001 owns canonical identity; DOMAIN-006 owns Provider context;
DOMAIN-008 owns market/session truth; DOMAIN-007 owns Risk. For Intraday,
ADR-0023 freezes that Risk authority as advisory loss-exposure observation
only. Product membership does not transfer any of those authorities.

## Responsibilities Not Owned

Swing product state and policy, canonical Instrument meaning, Provider lifecycle,
market schedules, DOMAIN-007 Risk-observation meaning, broker execution, and
reference-market trading consequence are not Intraday-owned. The Intraday
adapter owns product composition only and cannot create Risk permission.

## Governing ADRs

See the Living Architecture Record, Native Universe V1, and ownership registry.
