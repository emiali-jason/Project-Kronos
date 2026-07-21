# KRONOS Platform Architecture Overview
Status: Approved
Owner: Chief Architect
Version: 1.0

## Platform Vision

KRONOS Platform separates business meaning from platform support so that every responsibility has one owner, every dependency is contract-based, and implementation choices cannot redefine architecture.

The platform preserves the existing KRONOS decision and execution boundaries while providing a stable domain model for future products.

## Constitutional Principles

- CA-013 — Every domain has a stable identity and boundary.
- CA-014 — Responsibilities are classified as Business, Platform, or Oversight.
- CA-015 — Dependencies exist only through approved contracts.
- CA-016 — Every semantic responsibility has one owner.
- CA-017 — Communication mechanisms are platform responsibilities, not business logic.
- CA-018 — Domain completion does not depend on hidden human workflow.
- CA-019 — Platform Architecture v1.0 is frozen and changes require an approved ADR.

## Domain Map

| Class | Domains |
| --- | --- |
| Business | Instrument, Observation, Validation, Risk, Execution, Portfolio |
| Platform | Provider, Market, Event, Configuration |
| Oversight | Audit |

## Business Pipeline

**Instrument → Observation → Validation → Risk → Execution → Portfolio**

| Domain | Primary responsibility |
| --- | --- |
| Instrument | Establish instrument identity. |
| Observation | Publish market facts. |
| Validation | Publish business judgment. |
| Risk | Publish risk approval. |
| Execution | Own execution action and order semantics. |
| Portfolio | Publish resulting position and portfolio state. |

## Platform Responsibilities

| Domain | Primary responsibility |
| --- | --- |
| Provider | Own provider integration. |
| Market | Own market schedule semantics. |
| Event | Own platform event semantics. |
| Configuration | Own runtime configuration semantics. |
| Audit | Own the read-only Audit Trail. |

## Existing KRONOS Boundaries

- KR-370 owns direction and BUY READY / SELL READY.
- KR-380 owns final execution timing and BUY NOW / SELL NOW.
- KR-380 is the sole currently authorized consumer of the entry Execution Context.
- KR-390 owns the objective KRONOS model trade.
- KR-400 owns confirmed BUY NOW / SELL NOW alert events.
- PP-007 requires identical execution semantics across markets.
- ENGINE_OWNERSHIP and DATA_FLOW remain authoritative for current engine responsibilities and information paths.

## Platform Layers

| Layer | Purpose |
| --- | --- |
| Constitutional | Governs domain identity, ownership, dependencies, communication, workflow independence, and change control. |
| Business | Answers the six approved business questions from instrument identity through portfolio state. |
| Platform | Provides provider integration, market schedule, event, and configuration responsibilities without creating business judgment. |
| Oversight | Observes published contracts read-only through Audit. |
| Contract | Preserves semantic boundaries between every producer and consumer. |

## Start Here

1. [PLATFORM-000 — KRONOS Platform Constitution](PLATFORM-000-CONSTITUTION.md)
2. [Platform Business Pipeline](PLATFORM_BUSINESS_PIPELINE.md)
3. [Domain Dependency Matrix](DOMAIN_DEPENDENCY_MATRIX.md)
4. [Domain Ownership Matrix](DOMAIN_OWNERSHIP_MATRIX.md)
5. [Architecture Index](ARCHITECTURE_INDEX.md)
