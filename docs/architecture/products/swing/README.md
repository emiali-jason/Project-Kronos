# Swing Product Architecture

**Status:** Draft
**Owner:** TBD
**Approved By:** Not approved

## Purpose

This directory is the Draft documentation scaffold for the KRONOS Swing product area.

The folder name does not establish product responsibility, authority, interfaces, dependencies, or approved architecture.

## Documents

- [Responsibilities](RESPONSIBILITIES.md)
- [Interfaces](INTERFACES.md)
- [Constraints](CONSTRAINTS.md)
- [Future](FUTURE.md)
- [ADP-001A — Swing Phase 1 Market Data Inventory](SWING-PHASE-1-MARKET-DATA-INVENTORY.md) — Approved canonical architecture
- [ADP-001B — KRONOS Swing Instrument Identity Architecture](SWING-PHASE-1-INSTRUMENT-IDENTITY-ARCHITECTURE.md) — Approved canonical architecture
- [ADP-001C — Provider → Instrument Contract](SWING-PHASE-1-PROVIDER-INSTRUMENT-CONTRACT.md) — Superseded Version 1.0 historical predecessor; use [EAIC-002 Version 0.1](../../interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md)
- [ADP-001D — Instrument → Observation Contract](SWING-PHASE-1-INSTRUMENT-OBSERVATION-CONTRACT.md) — Approved canonical architecture
- [ADP-001E — Observation Domain Architecture](SWING-PHASE-1-OBSERVATION-DOMAIN-ARCHITECTURE.md) — Approved canonical architecture
- [ADP-001F — Configuration → Provider Runtime Configuration Boundary](SWING-PHASE-1-CONFIGURATION-PROVIDER-RUNTIME-CONFIGURATION-BOUNDARY.md) — Approved Canonical Architecture
- [ADP-001G — Configuration → Provider Authentication Boundary](SWING-PHASE-1-CONFIGURATION-PROVIDER-AUTHENTICATION-BOUNDARY.md) — Approved canonical architecture
- [ADP-001H — Provider Instrument Master Acquisition Capability and Contract](SWING-PHASE-1-PROVIDER-INSTRUMENT-MASTER-ACQUISITION-CAPABILITY-AND-CONTRACT.md) — Superseded Version 1.0 historical predecessor; successor authority: [ADR-009](../../platform/domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md), [DOMAIN-006](../../platform/domains/provider/ARCHITECTURE.md), and [EAIC-002](../../interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md)
- [ADP-001I — Swing Phase 1 Approved Instrument Universe and Reference Semantics Architecture](SWING-PHASE-1-APPROVED-INSTRUMENT-UNIVERSE-AND-REFERENCE-SEMANTICS-ARCHITECTURE.md) — Approved canonical architecture
- [ADP-001J — Instrument Interpretation and Canonical Identity Establishment Architecture](SWING-PHASE-1-INSTRUMENT-INTERPRETATION-AND-CANONICAL-IDENTITY-ESTABLISHMENT-ARCHITECTURE.md) — Approved canonical architecture

## Approved Architecture

- [ADP-001A — Swing Phase 1 Market Data Inventory](SWING-PHASE-1-MARKET-DATA-INVENTORY.md) — Canonical architecture for Phase 1 — Market Data Foundation
- [ADP-001B — KRONOS Swing Instrument Identity Architecture](SWING-PHASE-1-INSTRUMENT-IDENTITY-ARCHITECTURE.md) — Canonical Instrument Identity architecture for Phase 1 — Market Data Foundation
- [ADP-001C — Provider → Instrument Contract](SWING-PHASE-1-PROVIDER-INSTRUMENT-CONTRACT.md) — Superseded historical predecessor; [EAIC-002 Version 0.1](../../interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md) is the sole canonical Provider → Instrument submission contract and remains inactive pending separate activation authority
- [ADP-001D — Instrument → Observation Contract](SWING-PHASE-1-INSTRUMENT-OBSERVATION-CONTRACT.md) — Canonical governed attribution boundary for factual market information and approved canonical Instrument identity
- [ADP-001E — Observation Domain Architecture](SWING-PHASE-1-OBSERVATION-DOMAIN-ARCHITECTURE.md) — Canonical KRONOS Swing architecture for governed factual Observation ownership and semantics
- [ADP-001F — Configuration → Provider Runtime Configuration Boundary](SWING-PHASE-1-CONFIGURATION-PROVIDER-RUNTIME-CONFIGURATION-BOUNDARY.md) — Canonical Version 1.0 Configuration-owned Provider runtime-configuration boundary
- [ADP-001G — Configuration → Provider Authentication Boundary](SWING-PHASE-1-CONFIGURATION-PROVIDER-AUTHENTICATION-BOUNDARY.md) — Canonical Version 1.0 boundary for Configuration-owned authentication material and Provider-owned authenticated context
- [ADP-001H — Provider Instrument Master Acquisition Capability and Contract](SWING-PHASE-1-PROVIDER-INSTRUMENT-MASTER-ACQUISITION-CAPABILITY-AND-CONTRACT.md) — Superseded historical architecture; use [ADR-009 Version 1.0](../../platform/domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md), [DOMAIN-006 Provider Domain Architecture](../../platform/domains/provider/ARCHITECTURE.md), and [EAIC-002 Version 0.1](../../interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md)
- [ADP-001I — Swing Phase 1 Approved Instrument Universe and Reference Semantics Architecture](SWING-PHASE-1-APPROVED-INSTRUMENT-UNIVERSE-AND-REFERENCE-SEMANTICS-ARCHITECTURE.md) — Approved canonical architecture defining the KRONOS Swing Phase 1 semantic Instrument universe, MCX Analysis and Intended Execution roles, COMEX Reference roles, and provider-neutral reference semantics
- [ADP-001J — Instrument Interpretation and Canonical Identity Establishment Architecture](SWING-PHASE-1-INSTRUMENT-INTERPRETATION-AND-CANONICAL-IDENTITY-ESTABLISHMENT-ARCHITECTURE.md) — Approved canonical architecture for Instrument-owned interpretation and canonical identity establishment

## Governing ADRs

[TBD]
